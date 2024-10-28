# agent_monitor.py

import logging
import threading
import time
import psutil
from modules.utilities.logging_manager import setup_logging
from modules.agent.agent_manager import AgentManager

class AgentMonitor:
    """
    Monitors and provides agent-based metrics.
    """

    def __init__(self):
        self.logger = setup_logging('AgentMonitor')
        self.lock = threading.Lock()
        self.agent_manager = AgentManager()
        self.start_time = time.time()
        self.logger.info("AgentMonitor initialized successfully.")

    def get_agent_metrics(self):
        """
        Retrieves current agent metrics.

        Returns:
            dict: A dictionary of agent metrics.
        """
        try:
            with self.lock:
                metrics = {}

                # Active Agents
                active_agents = self.agent_manager.get_active_agents()
                metrics['Active Agents'] = len(active_agents)

                # Agent CPU Usage
                agent_cpu_usage = psutil.Process().cpu_percent(interval=None)
                metrics['Agent CPU Usage'] = f"{agent_cpu_usage}%"

                # Agent Memory Usage
                agent_memory_info = psutil.Process().memory_info()
                agent_memory_usage = agent_memory_info.rss
                metrics['Agent Memory Usage'] = self._format_bytes(agent_memory_usage)

                # Tasks in Queue
                tasks_in_queue = self.agent_manager.get_tasks_in_queue()
                metrics['Tasks in Queue'] = tasks_in_queue

                # Completed Tasks
                completed_tasks = self.agent_manager.get_completed_tasks()
                metrics['Completed Tasks'] = completed_tasks

                # Average Task Time
                avg_task_time = self.agent_manager.get_average_task_time()
                metrics['Average Task Time'] = f"{avg_task_time:.2f}s"

                # Error Count
                error_count = self.agent_manager.get_error_count()
                metrics['Error Count'] = error_count

                # Warning Count
                warning_count = self.agent_manager.get_warning_count()
                metrics['Warning Count'] = warning_count

                # Agent Uptime
                uptime = time.time() - self.start_time
                metrics['Agent Uptime'] = self._format_time(uptime)

                # Heartbeat Status
                heartbeat_status = self.agent_manager.get_heartbeat_status()
                metrics['Heartbeat Status'] = "Online" if heartbeat_status else "Offline"

                # Messages Sent
                messages_sent = self.agent_manager.get_messages_sent()
                metrics['Messages Sent'] = messages_sent

                # Messages Received
                messages_received = self.agent_manager.get_messages_received()
                metrics['Messages Received'] = messages_received

                # Failed Messages
                failed_messages = self.agent_manager.get_failed_messages()
                metrics['Failed Messages'] = failed_messages

                # Agent Network Usage
                net_io = psutil.Process().net_io_counters()
                agent_network_usage = net_io.bytes_sent + net_io.bytes_recv
                metrics['Agent Network Usage'] = self._format_bytes(agent_network_usage)

                # Agent Thread Count
                thread_count = psutil.Process().num_threads()
                metrics['Agent Thread Count'] = thread_count

                # Agent Handles Count
                handles_count = psutil.Process().num_handles() if hasattr(psutil.Process(), 'num_handles') else 'N/A'
                metrics['Agent Handles Count'] = handles_count

                # Agent Load Average
                metrics['Agent Load Average'] = f"{agent_cpu_usage}%"

                # Task Success Rate
                task_success_rate = self.agent_manager.get_task_success_rate()
                metrics['Task Success Rate'] = f"{task_success_rate:.2f}%"

                # Task Failure Rate
                task_failure_rate = self.agent_manager.get_task_failure_rate()
                metrics['Task Failure Rate'] = f"{task_failure_rate:.2f}%"

                # Cache Hit Rate
                cache_hit_rate = self.agent_manager.get_cache_hit_rate()
                metrics['Cache Hit Rate'] = f"{cache_hit_rate:.2f}%"

                # Cache Miss Rate
                cache_miss_rate = self.agent_manager.get_cache_miss_rate()
                metrics['Cache Miss Rate'] = f"{cache_miss_rate:.2f}%"

                # Pending I/O Operations
                pending_io_operations = self.agent_manager.get_pending_io_operations()
                metrics['Pending I/O Operations'] = pending_io_operations

                # Disk Read Bytes
                disk_io = psutil.Process().io_counters()
                metrics['Disk Read Bytes'] = self._format_bytes(disk_io.read_bytes)

                # Disk Write Bytes
                metrics['Disk Write Bytes'] = self._format_bytes(disk_io.write_bytes)

                # Open File Descriptors
                open_fds = psutil.Process().num_fds()
                metrics['Open File Descriptors'] = open_fds

                # Socket Connections
                connections = psutil.Process().connections()
                metrics['Socket Connections'] = len(connections)

                # API Call Count
                api_call_count = self.agent_manager.get_api_call_count()
                metrics['API Call Count'] = api_call_count

                # Database Query Count
                db_query_count = self.agent_manager.get_db_query_count()
                metrics['Database Query Count'] = db_query_count

                # Database Query Latency
                db_query_latency = self.agent_manager.get_db_query_latency()
                metrics['Database Query Latency'] = f"{db_query_latency:.2f}ms"

                # Event Loop Lag
                event_loop_lag = self.agent_manager.get_event_loop_lag()
                metrics['Event Loop Lag'] = f"{event_loop_lag:.2f}ms"

                # Garbage Collection Count
                gc_count = self.agent_manager.get_garbage_collection_count()
                metrics['Garbage Collection Count'] = gc_count

                # Memory Fragmentation
                memory_fragmentation = self.agent_manager.get_memory_fragmentation()
                metrics['Memory Fragmentation'] = f"{memory_fragmentation:.2f}%"

                # Agent CPU Temperature
                cpu_temp = self._get_cpu_temperature()
                metrics['Agent CPU Temperature'] = f"{cpu_temp}°C"

                self.logger.debug("Agent metrics collected successfully.")
                return metrics
        except Exception as e:
            self.logger.error(f"Error getting agent metrics: {e}", exc_info=True)
            return {}

    def _format_bytes(self, bytes_num):
        """
        Converts bytes to a human-readable format.
        """
        try:
            for unit in ['Bytes', 'KB', 'MB', 'GB', 'TB']:
                if bytes_num < 1024.0:
                    return f"{bytes_num:.2f} {unit}"
                bytes_num /= 1024.0
            return f"{bytes_num:.2f} PB"
        except Exception as e:
            self.logger.error(f"Error formatting bytes: {e}", exc_info=True)
            return "N/A"

    def _format_time(self, seconds):
        """
        Converts seconds to a human-readable time format.
        """
        try:
            hours, remainder = divmod(int(seconds), 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours}h {minutes}m {seconds}s"
        except Exception as e:
            self.logger.error(f"Error formatting time: {e}", exc_info=True)
            return "N/A"

    def _get_cpu_temperature(self):
        """
        Retrieves the CPU temperature.
        """
        try:
            temps = psutil.sensors_temperatures()
            if 'coretemp' in temps:
                return temps['coretemp'][0].current
            elif 'cpu-thermal' in temps:
                return temps['cpu-thermal'][0].current
            else:
                return 'N/A'
        except Exception as e:
            self.logger.error(f"Error getting CPU temperature: {e}", exc_info=True)
            return 'N/A'

