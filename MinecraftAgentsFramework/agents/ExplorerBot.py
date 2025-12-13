from BaseAgent import BaseAgent, AgentState
from collections import defaultdict
from functools import reduce
import mcpi.block as block
import datetime
import asyncio
import random

class ExplorerBot(BaseAgent):
    def __init__(self, mc, workspace):
        self.mc = mc
        super().__init__(workspace)
        self.display_task = None

    def perceive(self, command=None, **kwargs):
        messages = self.workspace.get_messages_for(self.__class__.__name__)
        for msg in messages:
            self.handle_message(msg)
        
        if command:
            action = command.get("action")
            if action == "set":
                parameters = command.get("parameters", {})
                if "range" in parameters:
                    try:
                        range_val = int(parameters["range"])
                        if range_val > 0:
                            self.args["range"] = range_val
                            print(f"[PERCEIVE] Updated range={range_val}")
                        else:
                            print(f"[PERCEIVE] Invalid range: {range_val}")
                    except (ValueError, TypeError) as e:
                        print(f"[PERCEIVE] Error parsing range: {e}")
                else:
                    print(f"[PERCEIVE] set command missing range parameter")

        self.x0 = kwargs.get("x", 0)
        self.z0 = kwargs.get("z", 0)
        self.area = kwargs.get("range", 32)

        heights = {}

        for dx in range(-self.area, self.area + 1):
            for dz in range(-self.area, self.area + 1):
                if (dx**2 + dz**2) <= self.area**2:
                    x = self.x0 + dx
                    z = self.z0 + dz
                    y = self.mc.getHeight(x, z)
                    heights[(x, z)] = y
        
        self.heights = heights
        self.blocks = self.identify_blocks(heights)
        return heights

    def decide(self, **kwargs):
        self.elevation_map = self.generate_elevation_map(self.heights)
        self.flat_regions = self.identify_flat_regions(self.elevation_map)

        self.UNSTABLE_IDS = {
            block.WATER.id,
            block.WATER_STATIONARY.id,
            block.LAVA.id,
            block.LAVA_STATIONARY.id,
            block.FIRE.id,
            block.CACTUS.id,
            block.ICE.id,
            block.SNOW.id,
            block.BEDROCK_INVISIBLE.id,
        }
        self.stable_regions = list(filter(self.is_region_stable, self.flat_regions))
        return self.stable_regions

    async def act(self, **kwargs):
        if (hasattr(self, 'stable_regions') and len(self.stable_regions) > 0):
            self.block_names = self.get_block_names()

            regions_payload = []

            for region in self.stable_regions:
                y = region['y']
                width = region['width']
                depth = region['depth']
                block_entries = []

                for (x, z) in region['blocks']:
                    block_data = self.blocks[(x, y, z)]

                    block_entries.append({
                        "x": x,
                        "z": z,
                        "id": block_data.id,
                        "name": self.block_names.get(block_data.id, "UNKNOWN"),
                        "data": block_data.data,
                    })
                
                regions_payload.append({
                    "y": y,
                    "blocks": block_entries,
                    "width": width,
                    "depth": depth
                })

            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"

            message = {
                "type": "map.v1",
                "source": "ExplorerBot",
                "target": "BuilderBot",
                "timestamp": timestamp,
                "payload": {
                    "regions": regions_payload
                },
                "status": "SUCCESS",
                "context": {
                    "task_id": str(id(self.task)) if self.task else None,
                    "state": self.state.value
                }
            }

            if self.display_task is not None and not self.display_task.done():
                self.display_task.cancel()
                try:
                    await self.display_task
                except asyncio.CancelledError:
                    pass
            
            self.display_task = asyncio.create_task(self.show_region_blocks(regions_payload, duration=10))

            return message
        else: return None

    def stop(self):
        
        if self.display_task is not None and not self.display_task.done():
            self.display_task.cancel()
        super().stop()
        
    def generate_elevation_map(self, heights):
        elevation_map = defaultdict(list)

        for (x, z), y in heights.items():
            elevation_map[y].append((x, z))

        return dict(elevation_map)
    
    def identify_flat_regions(self, elevation_map):
        flat_regions = []
        used_coords = set()

        for y, coords in elevation_map.items():
            coord_set = set(coords)       
            coords_sorted = sorted(coords, key=lambda c: (c[0] - self.x0)**2 + (c[1] - self.z0)**2)
            
            for x, z in coords_sorted:
                if (x, z) not in used_coords:
                    max_width = 1
                    max_depth = 1

                    while (x + max_width, z) in coord_set and (x + max_width, z) not in used_coords:
                        if all((x + max_width - dx - self.x0)**2 + (z - self.z0)**2 <= self.area**2 for dx in range(max_width + 1)):
                            max_width += 1
                        else:
                            break

                    while all(
                        (x + dx, z + max_depth) in coord_set and 
                        (x + dx, z + max_depth) not in used_coords
                        for dx in range(max_width)
                    ):
                        if all((x + dx - self.x0)**2 + (z + max_depth - self.z0)**2 <= self.area**2 for dx in range(max_width)):
                            max_depth += 1
                        else:
                            break

                    region_coords = [(x + dx, z + dz) for dx in range(max_width) for dz in range(max_depth)]
                    
                    region_coords_filtered = []
                    for rx, rz in region_coords:
                        dx = rx - self.x0
                        dz = rz - self.z0
                        if (dx**2 + dz**2) <= self.area**2:
                            region_coords_filtered.append((rx, rz))
                    
                    if len(region_coords_filtered) >= 1:
                        flat_regions.append({
                            'y': y, 
                            'blocks': region_coords_filtered, 
                            'width': max_width, 
                            'depth': max_depth
                        })
                        used_coords.update(region_coords_filtered)

        return flat_regions
    
    def identify_blocks(self, heights):
        blocks = {}

        for (x, z), y in heights.items():
            block = self.mc.getBlockWithData(x, y - 1, z)
            blocks[(x, y, z)] = block

        return blocks
    
    def is_region_stable(self, region):
        y = region['y']

        block_ids = map(
            lambda coord: self.blocks.get((coord[0], y, coord[1]), None),
            region['blocks']
        )

        return reduce(
            lambda acc, block_id: acc and (block_id not in self.UNSTABLE_IDS),
            block_ids,
            True
        )
    
    def get_block_names(self):
        all_blocks = block.__dict__.items()

        valid_blocks = filter(lambda block: hasattr(block[1], "id"), all_blocks)
        id_name_pairs = map(lambda block: (block[1].id, block[0]), valid_blocks)

        return dict(id_name_pairs)
    
    async def show_region_blocks(self, regions_payload, duration=10):
        original_blocks = {} 

        for r in regions_payload:
            for b in r['blocks']:
                x, y, z = b['x'], r['y'], b['z']
                block_key = (x, y, z)
                if block_key in self.blocks:
                    original_block = self.mc.getBlockWithData(x, y - 1, z)
                    original_blocks[block_key] = original_block

        for region in regions_payload:
            color = random.randint(0, 15)
            for b in region['blocks']:
                x, z = b['x'], b['z']
                
                if (x, region['y'], z) in original_blocks:
                    self.mc.setBlock(x, region['y'] - 1, z, block.WOOL.id, color)

        print(f"[VISUALIZE] Showing {len(original_blocks)} blocks for {duration}s...")
        
        # start_time = asyncio.get_event_loop().time()
        try:
            elapsed = 0
            check_interval = 0.53
            while elapsed < duration:
                await asyncio.sleep(check_interval)
                elapsed += check_interval
        except asyncio.CancelledError:
            print(f"[VISUALIZE] Visualization cancelled, restoring blocks...")
        finally:
            for (x, y, z), b in original_blocks.items():
                self.mc.setBlock(x, y - 1, z, b.id, b.data)
            # self.interrupt_event.clear()
            print(f"[VISUALIZE] Restored {len(original_blocks)} blocks")