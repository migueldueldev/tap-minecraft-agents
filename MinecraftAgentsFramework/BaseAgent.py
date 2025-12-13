from abc import abstractmethod
import datetime
from enum import Enum
import asyncio
import json

class AgentState(Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    WAITING = "WAITING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"

class BaseAgent:
    def __init__(self, workspace):
        self.state: AgentState = AgentState.IDLE
        self.task: asyncio.Task = None
        self.should_stop = False
        self.workspace = workspace
        self.args = {}
        self.interrupt_event = asyncio.Event()

    @abstractmethod
    def perceive(self):
        pass

    @abstractmethod
    def decide(self):
        pass
    
    @abstractmethod
    def act(self):
        pass

    def get_state(self) -> AgentState:
        return self.state

    def set_state(self, new_state: AgentState):
        self.state = new_state
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
        self.workspace.log_event("STATE_CHANGE", self.__class__.__name__, {"new_state": new_state.value, "timestamp": timestamp})
    
    async def start(self, **kwargs):
        if self.task and not self.task.done():
            print(f"Agent {self.__class__.__name__} (ID={id(self)}) is already running.")
            return

        self.args = kwargs
        self.should_stop = False
        self.interrupt_event.clear()
        self.set_state(AgentState.IDLE)
        self.task = asyncio.create_task(self.run_loop())
        print(f"Agent {self.__class__.__name__} (ID={id(self)}) started.")

    def stop(self):
        self.should_stop = True
        self.interrupt_event.set()
        self.set_state(AgentState.STOPPED)
        print(f"Agent {self.__class__.__name__} (ID={id(self)}) stopped.")

    def pause(self):
        self.set_state(AgentState.PAUSED)
        self.interrupt_event.set()
        print(f"Agent {self.__class__.__name__} (ID={id(self)}) paused.")

    def resume(self):
        if self.state == AgentState.PAUSED:
            self.set_state(AgentState.RUNNING)
            self.interrupt_event.clear()
            print(f"Agent {self.__class__.__name__} (ID={id(self)}) resumed.")

    async def run_loop(self):
        try:
            while True:
                pending_command = self.workspace.get_pending_command(self.__class__.__name__)
                unhandled_command = None
                if pending_command:
                    print(f"[{self.__class__.__name__}] Processing command: {pending_command}")
                    handled = self.handle_command(pending_command)
                    if not handled:
                        unhandled_command = pending_command

                if self.state == AgentState.PAUSED:
                    await asyncio.sleep(0.1)
                    continue

                if self.state in (AgentState.STOPPED, AgentState.ERROR):
                    await asyncio.sleep(1)
                    continue
                
                if not self.args:
                    if self.state != AgentState.IDLE:
                        self.set_state(AgentState.IDLE)
                    await asyncio.sleep(0.5)
                    continue

                if self.state != AgentState.RUNNING:
                    self.set_state(AgentState.RUNNING)
                
                self.perceive(command=unhandled_command, **self.args)
                self.decide(**self.args)
                action_message = await self.act(**self.args)

                if action_message is not None:
                    self.workspace.post_message(action_message)
                    print(json.dumps(action_message, indent=4))

                await asyncio.sleep(1)
        except Exception as e:
            print(f"Agent {self.__class__.__name__} (ID={id(self)}) encountered an error: {e}")
            self.workspace.log_event("ERROR", self.__class__.__name__, {"error": str(e)})
            self.set_state(AgentState.ERROR)

        finally:
            print(f"Agent {self.__class__.__name__} (ID={id(self)}) run_loop terminated.")
    
    def handle_command(self, command):
        action = command.get("action")
        if action == "start":
            self.should_stop = False
            self.interrupt_event.clear()
            self.args = command.get("parameters", {})

            if self.state in (AgentState.STOPPED, AgentState.PAUSED, AgentState.IDLE):
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
        return False
    def handle_message(self, message):
        pass