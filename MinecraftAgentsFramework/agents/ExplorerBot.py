from BaseAgent import BaseAgent
from collections import defaultdict
from functools import reduce
import mcpi.block as block
import datetime
import asyncio
import random

class ExplorerBot(BaseAgent):
    def __init__(self, mc):
        self.mc = mc
        super().__init__()

    def perceive(self, **kwargs):
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
        self.elevation_map = self.generate_elevation_map(heights)
        self.flat_regions = self.identify_flat_regions(self.elevation_map)
        self.blocks = self.identify_blocks(heights)
        return heights

    def decide(self, **kwargs):
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

            await self.show_region_blocks(regions_payload, duration=10)

            return message
        else: return None

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
            
            for x, z in coords:
                if (x, z) not in used_coords:
                    width = 1
                    while (x + width, z) in coord_set and (x + width, z) not in used_coords:
                        width += 1

                    depth = 1
                    while all((x + dx, z + depth) in coord_set and (x + dx, z + depth) not in used_coords for dx in range(width)):
                        depth += 1

                    if width >= 2 and depth >= 2:
                        region = [(x + dx, z + dz) for dx in range(width) for dz in range(depth)]
                        flat_regions.append({'y': y, 'blocks': region, 'width': width, 'depth': depth})
                        used_coords.update(region)

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
        original_blocks = {
            (b['x'], r['y'], b['z']): self.blocks[(b['x'], r['y'], b['z'])]
            for r in regions_payload
            for b in r['blocks']
        }

        for region in regions_payload:
            color = random.randint(0, 15)
            for b in region['blocks']:
                self.mc.setBlock(b['x'], region['y'] - 1, b['z'], block.WOOL.id, color)

        await asyncio.sleep(duration)

        for (x, y, z), b in original_blocks.items():
            self.mc.setBlock(x, y - 1, z, b.id, b.data)