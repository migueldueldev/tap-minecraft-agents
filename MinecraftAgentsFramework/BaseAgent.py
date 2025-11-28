from abc import abstractmethod
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
    def __init__(self):
        self.state: AgentState = AgentState.IDLE
        self.task: asyncio.Task = None
        self.should_stop = False
        self.args = {}

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
    
    async def start(self, **kwargs):
        if self.task and not self.task.done():
            print(f"Agent {self.__class__.__name__} (ID={id(self)}) is already running.")
            return

        self.args = kwargs
        self.should_stop = False
        self.set_state(AgentState.RUNNING)
        self.task = asyncio.create_task(self.run_loop())
        print(f"Agent {self.__class__.__name__} (ID={id(self)}) started.")

    async def stop(self):
        self.should_stop = True

        if self.task and self.task != asyncio.current_task():
            await self.task
        
        self.set_state(AgentState.STOPPED)
        print(f"Agent {self.__class__.__name__} (ID={id(self)}) stopped.")

    async def pause(self):
        self.set_state(AgentState.PAUSED)
        print(f"Agent {self.__class__.__name__} (ID={id(self)}) paused.")

    async def resume(self):
        if self.state == AgentState.PAUSED:
            self.set_state(AgentState.RUNNING)
            print(f"Agent {self.__class__.__name__} (ID={id(self)}) resumed.")

    async def update(self, **kwargs):
        self.args.update(kwargs)
        print(f"Agent {self.__class__.__name__} (ID={id(self)}) updated with options: {kwargs}.")

    async def run_loop(self):
        try:
            while not self.should_stop:
                if self.state == AgentState.PAUSED:
                    await asyncio.sleep(0.1)
                    continue

                if self.state in (AgentState.STOPPED, AgentState.ERROR):
                    break

                self.perceive(**self.args)

                self.decide()

                action_message = await self.act()

                if action_message is not None:
                    print(json.dumps(action_message, indent=4))

                await asyncio.sleep(0)

        except Exception as e:
            print(f"Agent {self.__class__.__name__} (ID={id(self)}) encountered an error: {e}")
            self.set_state(AgentState.ERROR)

        finally:
            if not self.should_stop:
                await self.stop()