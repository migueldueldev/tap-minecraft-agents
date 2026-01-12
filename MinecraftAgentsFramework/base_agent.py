from logging_config import get_logger
from abc import abstractmethod
from collections import deque
from enum import Enum
import datetime
import asyncio
import json
import threading

class AgentState(Enum):
    """Enumeration of possible agent states during execution lifecycle."""
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    WAITING = "WAITING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"

class BaseAgent:
    """
    Abstract base class for all Minecraft agents using the PDA (Perceive-Decide-Act) cycle.
    Provides common functionality for state management, command processing and inter-agent communication.
    """
    def __init__(self, mc, workspace):
        """Initialize the agent with Minecraft connection and shared workspace."""
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
        self.logger = get_logger(self.__class__.__name__)

    def receive_command(self, command):
        """Receive a command from the shared workspace and queue it for processing."""
        with self.lock:
            self.local_command_queue.append(command)
        self.command_event.set()

    def receive_message(self, message):
        """Receive a message from another agent and queue it for processing."""
        with self.lock:
            self.local_message_queue.append(message)

    def get_messages(self) -> list:
        """Retrieve and clear all pending messages from the local queue."""
        messages = []
        with self.lock:
            while self.local_message_queue:
                messages.append(self.local_message_queue.popleft())

        if messages:
            self.workspace.log_event("MESSAGES_CONSUMED", self.__class__.__name__, {"count": len(messages)})
            
        return messages

    @abstractmethod
    async def perceive(self):
        """Gather information from the environment. Must be implemented by subclasses."""
        pass

    @abstractmethod
    async def decide(self):
        """Process perceived information and make decisions. Must be implemented by subclasses."""
        pass
    
    @abstractmethod
    async def act(self):
        """Execute actions based on decisions. Must be implemented by subclasses."""
        pass

    def get_state(self) -> AgentState:
        """Return the current agent state."""
        return self.state

    def set_state(self, new_state: AgentState, reason: str = None):
        """Update agent state and log the transition in the workspace."""
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
        """Start the PDA cycle and command processing loop of the agent."""
        if self.state == AgentState.STOPPED:
            self.logger.warning("Agent (ID=%s) is stopped and cannot be restarted", id(self))
            return

        if self.pda_task and not self.pda_task.done():
            self.logger.warning("Agent (ID=%s) is already running", id(self))
            return

        self.args = kwargs
        self.should_stop = False
        self.interrupt_event.clear()
        self.set_state(AgentState.IDLE, reason="Agent started on initialization")
        
        self.command_task = asyncio.create_task(self.process_commands_loop())
        self.pda_task = asyncio.create_task(self.run_agent_cycle())
        self.mc.postToChat(f"Agent {self.__class__.__name__} started.")
        self.logger.info("Agent (ID=%s) started", id(self))

    def stop(self):
        """Stop the agent and terminate its execution cycle."""
        self.should_stop = True
        self.interrupt_event.set()
        self.set_state(AgentState.STOPPED, reason="Stop command received")
        self.mc.postToChat(f"Agent {self.__class__.__name__} stopped.")
        self.logger.info("Agent (ID=%s) stopped", id(self))

    def pause(self):
        """Pause the execution cycle of the agent."""
        if self.state != AgentState.PAUSED:
            self.set_state(AgentState.PAUSED, reason="Pause command received")
            self.interrupt_event.set()
            self.mc.postToChat(f"Agent {self.__class__.__name__} paused.")
            self.logger.info("Agent (ID=%s) paused", id(self))
        else:
            self.mc.postToChat(f"Agent {self.__class__.__name__} is already paused.")

    def resume(self):
        """Resume the execution cycle of the agent from paused state."""
        if self.state == AgentState.PAUSED:
            self.set_state(AgentState.RUNNING, reason="Resume command received")
            self.interrupt_event.set()
            self.mc.postToChat(f"Agent {self.__class__.__name__} resumed.")
            self.logger.info("Agent (ID=%s) resumed", id(self))
        else:
            self.mc.postToChat(f"Agent {self.__class__.__name__} is not paused.")

    def status(self):
        """Display the current agent status in the Minecraft chat."""
        self.mc.postToChat(f"Agent {self.__class__.__name__} status: {self.state.value}")
        self.logger.debug("Agent (ID=%s) status: %s", id(self), self.state.value)

    def help(self):
        """Display available commands for this agent in the Minecraft chat."""
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
        self.logger.debug("Agent (ID=%s) help text displayed", id(self))
    
    async def process_commands_loop(self):
        """Continuously process commands from the local command queue."""
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
                        self.logger.debug("Processing command: %s", pending_command)
                        self.handle_command(pending_command)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error("Agent (ID=%s) encountered an error in command processing: %s", id(self), e)
            self.workspace.log_event("ERROR", self.__class__.__name__, {"error": str(e), "origin": "command_processing_loop", "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"})
            self.set_state(AgentState.ERROR)

        finally:
            self.logger.debug("Agent (ID=%s) command processing loop terminated", id(self))

    async def run_agent_cycle(self):
        """Execute the main Perceive-Decide-Act (PDA) loop until the agent is stopped."""
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
            self.logger.error("Agent (ID=%s) encountered an error in agent cycle: %s", id(self), e)
            self.workspace.log_event("ERROR", self.__class__.__name__, {"error": str(e), "origin": "agent_run_loop", "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"})
            self.set_state(AgentState.ERROR)

        finally:
            self.logger.debug("Agent (ID=%s) execution loop terminated", id(self))
    
    def handle_command(self, command):
        """Process a command and execute the corresponding action."""
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
