from abc import abstractmethod
import datetime
from enum import Enum
import asyncio
import json
import threading
from collections import deque

class AgentState(Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    WAITING = "WAITING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"

class BaseAgent:
    def __init__(self, mc, workspace):
        self.state: AgentState = AgentState.IDLE
        self.pda_task: asyncio.Task = None
        self.command_task: asyncio.Task = None
        self.should_stop = False
        self.mc = mc
        self.workspace = workspace
        self.workspace.register_observer(self)
        self.local_command_queue = deque()
        self.local_message_queue = deque()
        self.lock = threading.Lock()
        self.args = {}
        self.interrupt_event = asyncio.Event()
        self.command_event = asyncio.Event()

    def receive_command(self, command):
        with self.lock:
            self.local_command_queue.append(command)
        self.command_event.set()

    def receive_message(self, message):
        with self.lock:
            self.local_message_queue.append(message)

    def get_messages(self) -> list:
        messages = []
        with self.lock:
            while self.local_message_queue:
                messages.append(self.local_message_queue.popleft())

        if messages:
            self.workspace.log_event("MESSAGES_CONSUMED", self.__class__.__name__, {"count": len(messages)})
            
        return messages

    @abstractmethod
    async def perceive(self):
        pass

    @abstractmethod
    async def decide(self):
        pass
    
    @abstractmethod
    async def act(self):
        pass

    def get_state(self) -> AgentState:
        return self.state

    def set_state(self, new_state: AgentState, reason: str = None):
        old_state = self.state
        self.state = new_state
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
        log_data = {
            "previous_state": old_state.value,
            "new_state": new_state.value,
            "timestamp": timestamp
        }
        if reason:
            log_data["reason"] = reason
        self.workspace.log_event("STATE_CHANGE", self.__class__.__name__, log_data)
    
    async def start(self, **kwargs):
        if self.state == AgentState.STOPPED:
            print(f"Agent {self.__class__.__name__} (ID={id(self)}) is stopped and cannot be restarted.")
            return

        if self.pda_task and not self.pda_task.done():
            print(f"Agent {self.__class__.__name__} (ID={id(self)}) is already running.")
            return

        self.args = kwargs
        self.should_stop = False
        self.interrupt_event.clear()
        self.set_state(AgentState.IDLE, reason="Agent started on initialization")
        
        self.command_task = asyncio.create_task(self.process_commands_loop())
        self.pda_task = asyncio.create_task(self.run_agent_cycle())
        self.mc.postToChat(f"Agent {self.__class__.__name__} started.")
        print(f"Agent {self.__class__.__name__} (ID={id(self)}) started.")

    def stop(self):
        self.should_stop = True
        self.interrupt_event.set()
        self.set_state(AgentState.STOPPED, reason="Stop command received")
        self.mc.postToChat(f"Agent {self.__class__.__name__} stopped.")
        print(f"Agent {self.__class__.__name__} (ID={id(self)}) stopped.")

    def pause(self):
        if self.state != AgentState.PAUSED:
            self.set_state(AgentState.PAUSED, reason="Pause command received")
            self.interrupt_event.set()
            self.mc.postToChat(f"Agent {self.__class__.__name__} paused.")
            print(f"Agent {self.__class__.__name__} (ID={id(self)}) paused.")
        else:
            self.mc.postToChat(f"Agent {self.__class__.__name__} is already paused.")

    def resume(self):
        if self.state == AgentState.PAUSED:
            self.set_state(AgentState.RUNNING, reason="Resume command received")
            self.interrupt_event.set()
            self.mc.postToChat(f"Agent {self.__class__.__name__} resumed.")
            print(f"Agent {self.__class__.__name__} (ID={id(self)}) resumed.")
        else:
            self.mc.postToChat(f"Agent {self.__class__.__name__} is not paused.")

    def status(self):
        self.mc.postToChat(f"Agent {self.__class__.__name__} status: {self.state.value}")
        print(f"Agent {self.__class__.__name__} (ID={id(self)}) status is {self.state.value}.")

    def help(self):
        help_message = [
            f"Agent {self.__class__.__name__} help commands:",
            "   start: Start the agent",
            "   stop: Stop the agent",
            "   pause: Pause the agent",
            "   resume: Resume the agent",
            "   status: Get the status of the agent",
        ]
        for line in help_message:
            self.mc.postToChat(line)
        print(f"Agent {self.__class__.__name__} (ID={id(self)}) help text displayed.")
    
    async def process_commands_loop(self):
        try:
            while True:
                await self.command_event.wait()
                self.command_event.clear()
                
                while True:
                    pending_command = None
                    with self.lock:
                        if self.local_command_queue:
                            pending_command = self.local_command_queue.popleft()
                        else:
                            break
                    
                    if pending_command:
                        self.workspace.log_event("COMMAND_CONSUMED", self.__class__.__name__, pending_command)
                        print(f"[{self.__class__.__name__}] Processing command: {pending_command}")
                        self.handle_command(pending_command)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Agent {self.__class__.__name__} (ID={id(self)}) encountered an error: {e}")
            self.workspace.log_event("ERROR", self.__class__.__name__, {"error": str(e), "origin": "command_processing_loop", "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"})
            self.set_state(AgentState.ERROR)

        finally:
            print(f"Agent {self.__class__.__name__} (ID={id(self)}) command processing loop terminated.")

    async def run_agent_cycle(self):
        try:
            while not self.should_stop:
                if self.state == AgentState.PAUSED:
                    await self.interrupt_event.wait()
                    self.interrupt_event.clear()
                    continue

                if self.state == AgentState.STOPPED:
                    break

                if self.state == AgentState.ERROR:
                    await asyncio.sleep(1)
                    continue
                
                if not self.args:
                    if self.state != AgentState.IDLE:
                        self.set_state(AgentState.IDLE)
                    await asyncio.sleep(0.5)
                    continue

                if self.state != AgentState.RUNNING:
                    self.set_state(AgentState.RUNNING)
                
                await self.perceive(**self.args)
                await self.decide(**self.args)
                await self.act(**self.args)

                await asyncio.sleep(0.1)
        except Exception as e:
            print(f"Agent {self.__class__.__name__} (ID={id(self)}) encountered an error: {e}")
            self.workspace.log_event("ERROR", self.__class__.__name__, {"error": str(e), "origin": "agent_run_loop", "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"})
            self.set_state(AgentState.ERROR)

        finally:
            print(f"Agent {self.__class__.__name__} (ID={id(self)}) execution loop terminated.")
    
    def handle_command(self, command):
        payload = command.get("payload", {})
        action = payload.get("action")
        parameters = payload.get("parameters", {})

        if self.state == AgentState.STOPPED and action not in ["status", "help"]:
            self.mc.postToChat(f'Agent {self.__class__.__name__} is stopped. Command "{action}" ignored.')
            return False

        if action == "start":
            self.should_stop = False
            self.interrupt_event.clear()
            self.args.update(parameters)
            if self.state == AgentState.IDLE:
                self.set_state(AgentState.RUNNING)
            return True
        elif action == "stop":
            self.stop()
            return True
        elif action == "pause":
            self.pause()
            return True
        elif action == "resume":
            self.resume()
            return True
        elif action == "status":
            self.status()
            return True
        elif action == "help":
            self.help()
            return True
            
        return False

    def handle_message(self, message):
        pass