from BaseAgent import BaseAgent
from collections import defaultdict
from mcpi.minecraft import Minecraft
import mcpi.block as block
import datetime
import asyncio
import random
import threading
import os
import math

class ExplorerBot(BaseAgent):
    def __init__(self, mc, workspace):
        self.mc = mc
        super().__init__(workspace)
        self.show_regions_thread = None
        self.show_regions_stop_event = None
        self.heights = {}
        self.blocks = {}

    async def perceive(self, command=None, **kwargs):
        messages = await self.get_messages()
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

        all_coords = []
        for dx in range(-self.area, self.area + 1):
            for dz in range(-self.area, self.area + 1):
                if dx*dx + dz*dz <= self.area*self.area:
                    all_coords.append((self.x0 + dx, self.z0 + dz))

        self.heights, self.blocks = await asyncio.to_thread(self._scan_world, all_coords)
        return self.heights
    
    async def decide(self, **kwargs):
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
        if hasattr(self, 'stable_regions') and self.stable_regions:
            self.block_names = self.get_block_names()

            regions_payload = []
            for region in self.stable_regions:
                y = region['y']
                region_blocks = []
                for x, z in region['blocks']:
                    block_data = self.blocks.get((x, y, z))
                    if block_data:
                        region_blocks.append({
                            "x": x,
                            "z": z,
                            "id": block_data.id,
                            "name": self.block_names.get(block_data.id, "UNKNOWN"),
                            "data": block_data.data,
                        })
                
                regions_payload.append({
                    "y": y,
                    "blocks": region_blocks,
                    "width": region['width'],
                    "depth": region['depth']
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

            if self.show_regions_thread and self.show_regions_thread.is_alive():
                self.show_regions_stop_event.set()
                await asyncio.to_thread(self.show_regions_thread.join)
            
            self.show_regions_stop_event = threading.Event()

            self.show_regions_thread = threading.Thread(
                target=self._show_region_blocks_sync,
                args=(regions_payload, 10, self.show_regions_stop_event)
            )
            self.show_regions_thread.start()

            return message
        else: return None

    def stop(self):
        if self.show_regions_thread and self.show_regions_thread.is_alive():
            self.show_regions_stop_event.set()
        super().stop()
        
    def generate_elevation_map(self, heights):
        elevation_map = defaultdict(list)

        for (x, z), y in heights.items():
            elevation_map[y].append((x, z))

        return dict(elevation_map)
    
    def identify_flat_regions(self, elevation_map):
        flat_regions = []
        
        min_x = self.x0 - self.area
        min_z = self.z0 - self.area
        size = 2 * self.area + 1
        
        for y, coords in elevation_map.items():
            grid = [[0] * size for _ in range(size)]
            count = 0
            for x, z in coords:
                grid[z - min_z][x - min_x] = 1
                count += 1
            
            while count > 0:
                best_rect = self.find_largest_rectangle_in_grid(grid, size, size)
                
                if not best_rect:
                    break
                    
                rx, rz, rwidth, rdepth = best_rect
                
                world_x = rx + min_x
                world_z = rz + min_z
                
                region_blocks = []
                for dz in range(rdepth):
                    for dx in range(rwidth):
                        if grid[rz + dz][rx + dx] == 1:
                            grid[rz + dz][rx + dx] = 0
                            region_blocks.append((world_x + dx, world_z + dz))
                            count -= 1
                
                if region_blocks:
                    flat_regions.append({
                        'y': y,
                        'blocks': region_blocks,
                        'width': rwidth,
                        'depth': rdepth
                    })
                
        return flat_regions

    def find_largest_rectangle_in_grid(self, grid, rows, cols):
        max_area = 0
        best_rect = None
        
        heights = [0] * (cols + 1)
        
        for r in range(rows):
            for c in range(cols):
                if grid[r][c] == 1:
                    heights[c] += 1
                else:
                    heights[c] = 0
            
            stack = []
            for c in range(cols + 1):
                while stack and heights[c] < heights[stack[-1]]:
                    h = heights[stack.pop()]
                    w = c if not stack else c - stack[-1] - 1
                    area = h * w
                    if area > max_area:
                        max_area = area
                        x_start = 0 if not stack else stack[-1] + 1
                        best_rect = (x_start, r - h + 1, w, h)
                stack.append(c)
                
        return best_rect
    
    def is_region_stable(self, region):
        y = region['y']
        for x, z in region['blocks']:
            block_data = self.blocks.get((x, y, z))
            if block_data and block_data.id in self.UNSTABLE_IDS:
                return False
        return True
    
    def get_block_names(self):
        return {b.id: name for name, b in block.__dict__.items() if hasattr(b, "id")}
    
    def scan_chunk(coords, results, lock):
        try:
            mc_instance = Minecraft.create()
            chunk_heights = {}
            chunk_blocks = {}
            for x, z in coords:
                y = mc_instance.getHeight(x, z)
                chunk_heights[(x, z)] = y
                chunk_blocks[(x, y, z)] = mc_instance.getBlockWithData(x, y - 1, z)
            with lock:
                results.append((chunk_heights, chunk_blocks))
        except Exception as e:
            print(f"Scanning error: {e}")
            with lock:
                results.append(({}, {}))

    def _scan_world(self, all_coords):
        if not all_coords:
            return {}, {}

        cpu_count = os.cpu_count() or 1
        num_threads = min(len(all_coords), cpu_count * 2)
        num_threads = max(1, num_threads)
            
        chunk_size = math.ceil(len(all_coords) / num_threads)
        chunks = [all_coords[i:i + chunk_size] for i in range(0, len(all_coords), chunk_size)]

        threads = []
        results = []
        lock = threading.Lock()

        for chunk in chunks:
            t = threading.Thread(target=self.scan_chunk, args=(chunk, results, lock))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
            
        heights = {}
        blocks = {}
        for h, b in results:
            heights.update(h)
            blocks.update(b)
        
        return heights, blocks

    def _show_region_blocks_sync(self, regions_payload, duration, stop_event):
        try:
            mc = Minecraft.create()
        except Exception as e:
            print(f"[VISUALIZE] Failed to connect to Minecraft: {e}")
            return

        original_blocks = {} 
        try:
            for r in regions_payload:
                for b in r['blocks']:
                    x, y, z = b['x'], r['y'], b['z']
                    try:
                        original_block = mc.getBlockWithData(x, y - 1, z)
                        original_blocks[(x, y, z)] = original_block
                    except Exception as e:
                        print(f"[VISUALIZE] Failed to get block at ({x}, {y - 1}, {z}): {e}")

            for region in regions_payload:
                color = random.randint(0, 15)
                for b in region['blocks']:
                    x, z = b['x'], b['z']
                    if (x, region['y'], z) in original_blocks:
                        mc.setBlock(x, region['y'] - 1, z, block.WOOL.id, color)

            print(f"[VISUALIZE] Showing {len(original_blocks)} blocks for {duration}s...")
            
            if stop_event.wait(duration):
                print(f"[VISUALIZE] Visualization cancelled, restoring blocks...")
            else:
                print(f"[VISUALIZE] Visualization completed, restoring blocks...")

        except Exception as e:
            print(f"[VISUALIZE] Error: {e}")
        finally:
            for (x, y, z), b in original_blocks.items():
                mc.setBlock(x, y - 1, z, b.id, b.data)
            print(f"[VISUALIZE] Restored {len(original_blocks)} blocks")