from base_agent import BaseAgent
from utils import create_message
from collections import defaultdict
from mcpi.minecraft import Minecraft
import mcpi.block as block
import datetime
import asyncio
import random
import threading
import json
import os
import math

class ExplorerBot(BaseAgent):
    def __init__(self, mc, workspace):
        super().__init__(mc, workspace)
        self.mc = mc
        self.workspace = workspace
        self.heights = {}
        self.blocks = {}
        self.displayed_regions = []
        self.current_exploration_task = None
        self.exploration_event = asyncio.Event()
        self.has_new_scan = False
        self.show_regions = False
        self.display_duration = 15.0
        self.pending_command = None
        self.request_queue = []
        self.waiting_confirmation = False

    async def perceive(self, **kwargs):
        self.exploration_event.clear()
        self.has_new_scan = True
        
        self.clear_visualization()

        self.x0 = kwargs.get("x", 0)
        self.z0 = kwargs.get("z", 0)
        self.area = kwargs.get("range", 32)

        all_coords = []
        for dx in range(-self.area, self.area + 1):
            for dz in range(-self.area, self.area + 1):
                if dx*dx + dz*dz <= self.area*self.area:
                    all_coords.append((self.x0 + dx, self.z0 + dz))

        self.heights, self.blocks = await asyncio.to_thread(self.scan_world, all_coords)
        return self.heights
    
    async def decide(self, **kwargs):
        if not self.has_new_scan or not self.heights:
            self.stable_regions = None
            return None

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
        message = None
        interrupted_by_command = False
        
        if hasattr(self, 'stable_regions') and self.stable_regions:
            message = self.generate_message()
            self.mc.postToChat(f"Exploration finished. Found {len(self.stable_regions)} stable flat regions.")

            if self.show_regions:
                await asyncio.to_thread(self.update_visualization)
                
                try:
                    wait_task = asyncio.create_task(asyncio.sleep(self.display_duration))
                    explore_event_task = asyncio.create_task(self.exploration_event.wait())
                    interrupt_event_task = asyncio.create_task(self.interrupt_event.wait())
                    
                    done, pending = await asyncio.wait(
                        [wait_task, explore_event_task, interrupt_event_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    
                    for task in pending:
                        task.cancel()
                    
                    if self.exploration_event.is_set():
                        interrupted_by_command = True
                        self.exploration_event.clear()
                        
                finally:
                    await asyncio.to_thread(self.clear_visualization)
        else:
            self.mc.postToChat("Exploration finished. No stable flat regions found.")

        if not interrupted_by_command:
            if self.request_queue:
                next_command = self.request_queue.pop(0)
                
                payload = next_command.get("payload", {})
                parameters = payload.get("parameters", {})
                
                self.args.update(parameters)
                self.mc.postToChat(f"Starting queued exploration. {len(self.request_queue)} requests remaining.")
            else:
                self.args.clear()

        if message:
            self.workspace.post_message(message)
            print(json.dumps(message, indent=4))
        return message
    
    def handle_command(self, command):
        payload = command.get("payload", {})
        action = payload.get("action")
        parameters = payload.get("parameters", {})

        if action == "confirm":
            if self.waiting_confirmation and self.pending_command:
                self.mc.postToChat("Current exploration interrupted. Starting new exploration.")
                
                pending_payload = self.pending_command.get("payload", {})
                parameters = pending_payload.get("parameters", {})
                
                self.args.update(parameters)
                self.exploration_event.set()
                
                self.pending_command = None
                self.waiting_confirmation = False
            else:
                self.mc.postToChat("No pending exploration request to confirm.")
            return True
        
        elif action == "queue":
            if self.waiting_confirmation and self.pending_command:
                self.request_queue.append(self.pending_command)
                self.mc.postToChat(f"Exploration request queued. Position: {len(self.request_queue)}")
                
                self.pending_command = None
                self.waiting_confirmation = False
            else:
                self.mc.postToChat("No pending exploration request to queue.")
            return True
        
        is_exploration_request = action in ["start", "set"]
        if is_exploration_request and self.args:
             self.pending_command = command
             self.waiting_confirmation = True
             self.mc.postToChat('Exploration is active. Type "./explorer confirm" to interrupt or "./explorer queue" to queue.')
             return True

        if super().handle_command(command):
            if action in ["start", "set"]:
                self.exploration_event.set()
            return True
        
        if action == "set":
            self.args.update(parameters)
            self.exploration_event.set()
            return True
        elif action == "toggle":
            if "display" in parameters:
                duration = parameters["display"]
                if duration is not None and isinstance(duration, (int, float)):
                    self.display_duration = float(duration)
                
                self.show_regions = not self.show_regions
                status = "enabled" if self.show_regions else "disabled"
                self.mc.postToChat(f"Option to show flat regions has been {status} with duration of {self.display_duration} seconds.")
            return True
            
        return False

    def clear_visualization(self):
        if self.displayed_regions:
            for region in self.displayed_regions:
                if not region['blocks']: continue
                
                try:
                    first_block = next(iter(region['blocks'].values()))
                    is_uniform = all(b.id == first_block.id and b.data == first_block.data for b in region['blocks'].values())
                    
                    min_x, min_z, max_x, max_z, y = region['bounds']
                
                    if is_uniform:
                        self.mc.setBlocks(min_x, y - 1, min_z, max_x, y - 1, max_z, first_block.id, first_block.data)
                    else:
                        for (x, _, z), b in region['blocks'].items():
                            self.mc.setBlock(x, y - 1, z, b.id, b.data)
                except Exception as e:
                    print(f"Error restoring original region blocks: {e}")
            self.displayed_regions.clear()

    def update_visualization(self):
        self.clear_visualization()
        
        for region in self.stable_regions:
            if not region['blocks']: continue
            
            min_x = region['blocks'][0][0]
            min_z = region['blocks'][0][1]
            width = region['width']
            depth = region['depth']
            y = region['y']
            
            max_x = min_x + width - 1
            max_z = min_z + depth - 1
            
            blocks = {}
            for x in range(min_x, max_x + 1):
                for z in range(min_z, max_z + 1):
                    block_data = self.blocks.get((x, y, z))
                    if block_data:
                        blocks[(x, y - 1, z)] = block_data
            
            self.displayed_regions.append({
                'bounds': (min_x, min_z, max_x, max_z, y),
                'blocks': blocks
            })
            
            color = random.randint(0, 15)
            try:
                self.mc.setBlocks(min_x, y - 1, min_z, max_x, y - 1, max_z, block.WOOL.id, color)
            except: pass

    def generate_message(self):
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

        context = {
            "task_id": str(id(self.pda_task)) if self.pda_task else None,
            "state": self.state.value
        }
        message = create_message(
            "map.v1", 
            "ExplorerBot", 
            "BuilderBot", 
            {"regions": regions_payload}, 
            status="SUCCESS",
            context=context
        )
        return message

    def stop(self):
        self.clear_visualization()
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
                largest_rect = self.find_largest_rectangle(grid, size, size)
                
                if not largest_rect:
                    break
                    
                rx, rz, rwidth, rdepth = largest_rect
                
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

    def find_largest_rectangle(self, grid, rows, cols):
        max_area = 0
        largest_rect = None
        
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
                        largest_rect = (x_start, r - h + 1, w, h)
                stack.append(c)
                
        return largest_rect
    
    def is_region_stable(self, region):
        y = region['y']
        for x, z in region['blocks']:
            block_data = self.blocks.get((x, y, z))
            if block_data and block_data.id in self.UNSTABLE_IDS:
                return False
        return True
    
    def get_block_names(self):
        return {b.id: name for name, b in block.__dict__.items() if hasattr(b, "id")}
    
    def scan_chunk(self, coords, results, lock):
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
            print(f"Chunk area scanning error: {e}")
            with lock:
                results.append(({}, {}))

    def scan_world(self, all_coords):
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