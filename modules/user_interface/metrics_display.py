# metrics_display.py

import logging
import threading
import tkinter as tk
from tkinter import ttk
import psutil
from modules.utilities.logging_manager import setup_logging
from modules.agent.agent_monitor import AgentMonitor
from modules.utilities.formatting_utils import format_bytes, format_time, format_datetime


class MetricsDisplay:
    """
    Displays real-time system and agent metrics in the user interface.
    """

    def __init__(self, parent):
        self.logger = setup_logging('MetricsDisplay')
        self.parent = parent
        self.metrics_frame = None
        self.metric_labels = {}
        self.lock = threading.Lock()
        self.agent_monitor = AgentMonitor()
        self.logger.info("MetricsDisplay initialized successfully.")

    def create_widgets(self, parent_frame):
        """
        Creates the widgets for displaying metrics.
        """
        try:
            self.logger.debug("Creating metrics display widgets.")
            self.metrics_frame = ttk.LabelFrame(parent_frame, text="Metrics", padding="10")
            self.metrics_frame.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

            # System Metrics to display
            system_metrics = [
                'CPU Usage',
                'CPU Frequency',
                'Per-Core Usage',
                'CPU Temperature',
                'Memory Usage',
                'Available Memory',
                'Used Memory',
                'Memory Free',
                'Swap Usage',
                'Disk Usage',
                'Disk Read Bytes',
                'Disk Write Bytes',
                'Disk Read Time',
                'Disk Write Time',
                'Network Sent',
                'Network Received',
                'Network Packets Sent',
                'Network Packets Received',
                'Network Errors In',
                'Network Errors Out',
                'Network Drops In',
                'Network Drops Out',
                'Battery Percentage',
                'Battery Time Left',
                'Process Count',
                'Thread Count',
                'Handles Count',
                'System Uptime',
                'Boot Time',
                'Load Average 1m',
                'Load Average 5m',
                'Load Average 15m',
                'Context Switches',
                'Interrupts',
                'Soft Interrupts',
                'Syscalls',
                'GPU Usage',
                'GPU Memory Total',
                'GPU Memory Used',
                'GPU Memory Free',
                'GPU Temperature'
            ]

            # Agent Metrics to display
            agent_metrics = [
                'Active Agents',
                'Agent CPU Usage',
                'Agent Memory Usage',
                'Tasks in Queue',
                'Completed Tasks',
                'Average Task Time',
                'Error Count',
                'Warning Count',
                'Agent Uptime',
                'Heartbeat Status',
                'Messages Sent',
                'Messages Received',
                'Failed Messages',
                'Agent Network Usage',
                'Agent Thread Count',
                'Agent Handles Count',
                'Agent Load Average',
                'Task Success Rate',
                'Task Failure Rate',
                'Cache Hit Rate',
                'Cache Miss Rate',
                'Pending I/O Operations',
                'Disk Read Bytes',
                'Disk Write Bytes',
                'Open File Descriptors',
                'Socket Connections',
                'API Call Count',
                'Database Query Count',
                'Database Query Latency',
                'Event Loop Lag',
                'Garbage Collection Count',
                'Memory Fragmentation',
                'Agent CPU Temperature',
                # Additional agent metrics can be added here
            ]

            # Create labels for system metrics
            system_frame = ttk.LabelFrame(self.metrics_frame, text="System Metrics")
            system_frame.pack(fill=tk.BOTH, expand=True, side=tk.TOP, padx=5, pady=5)

            for metric in system_metrics:
                frame = ttk.Frame(system_frame)
                frame.pack(fill=tk.X, padx=5, pady=2)

                label = ttk.Label(frame, text=f"{metric}:", width=25)
                label.pack(side=tk.LEFT)

                value = ttk.Label(frame, text="N/A")
                value.pack(side=tk.LEFT, padx=10)

                self.metric_labels[metric] = value

            # Create labels for agent metrics
            agent_frame = ttk.LabelFrame(self.metrics_frame, text="Agent Metrics")
            agent_frame.pack(fill=tk.BOTH, expand=True, side=tk.BOTTOM, padx=5, pady=5)

            for metric in agent_metrics:
                frame = ttk.Frame(agent_frame)
                frame.pack(fill=tk.X, padx=5, pady=2)

                label = ttk.Label(frame, text=f"{metric}:", width=25)
                label.pack(side=tk.LEFT)

                value = ttk.Label(frame, text="N/A")
                value.pack(side=tk.LEFT, padx=10)

                self.metric_labels[metric] = value

            self.logger.info("Metrics display widgets created successfully.")
        except Exception as e:
            self.logger.error(f"Error creating metrics display widgets: {e}", exc_info=True)
            raise

    def update_metrics(self):
        """
        Updates the displayed metrics.
        """
        try:
            self.logger.debug("Updating metrics display.")
            with self.lock:
                # System Metrics
                cpu_usage = psutil.cpu_percent(interval=None)
                cpu_freq = psutil.cpu_freq().current if psutil.cpu_freq() else 'N/A'
                per_core_usage = psutil.cpu_percent(interval=None, percpu=True)
                cpu_temp = self._get_cpu_temperature()
                memory = psutil.virtual_memory()
                swap = psutil.swap_memory()
                disk = psutil.disk_usage('/')
                disk_io = psutil.disk_io_counters()
                net_io = psutil.net_io_counters()
                battery = psutil.sensors_battery()
                processes = len(psutil.pids())
                threads = sum(p.num_threads() for p in psutil.process_iter())
                handles = self._get_handles_count()
                uptime = self._get_system_uptime()
                boot_time = psutil.boot_time()
                load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else (0, 0, 0)
                ctx_switches = psutil.cpu_stats().ctx_switches
                interrupts = psutil.cpu_stats().interrupts
                soft_interrupts = psutil.cpu_stats().soft_interrupts
                syscalls = psutil.cpu_stats().syscalls
                gpu_metrics = self._get_gpu_metrics()

                # Update system metric labels
                self.metric_labels['CPU Usage'].config(text=f"{cpu_usage}%")
                self.metric_labels['CPU Frequency'].config(text=f"{cpu_freq:.2f} MHz")
                self.metric_labels['Per-Core Usage'].config(text=', '.join([f"{usage}%" for usage in per_core_usage]))
                self.metric_labels['CPU Temperature'].config(text=f"{cpu_temp}°C")
                self.metric_labels['Memory Usage'].config(text=f"{memory.percent}%")
                self.metric_labels['Available Memory'].config(text=format_bytes(memory.available))
                self.metric_labels['Used Memory'].config(text=format_bytes(memory.used))
                self.metric_labels['Memory Free'].config(text=format_bytes(memory.free))
                self.metric_labels['Swap Usage'].config(text=f"{swap.percent}%")
                self.metric_labels['Disk Usage'].config(text=f"{disk.percent}%")
                self.metric_labels['Disk Read Bytes'].config(text=format_bytes(disk_io.read_bytes))
                self.metric_labels['Disk Write Bytes'].config(text=format_bytes(disk_io.write_bytes))
                self.metric_labels['Disk Read Time'].config(text=f"{disk_io.read_time} ms")
                self.metric_labels['Disk Write Time'].config(text=f"{disk_io.write_time} ms")
                self.metric_labels['Network Sent'].config(text=format_bytes(net_io.bytes_sent))
                self.metric_labels['Network Received'].config(text=format_bytes(net_io.bytes_recv))
                self.metric_labels['Network Packets Sent'].config(text=f"{net_io.packets_sent}")
                self.metric_labels['Network Packets Received'].config(text=f"{net_io.packets_recv}")
                self.metric_labels['Network Errors In'].config(text=f"{net_io.errin}")
                self.metric_labels['Network Errors Out'].config(text=f"{net_io.errout}")
                self.metric_labels['Network Drops In'].config(text=f"{net_io.dropin}")
                self.metric_labels['Network Drops Out'].config(text=f"{net_io.dropout}")
                self.metric_labels['Battery Percentage'].config(text=f"{battery.percent}%" if battery else "N/A")
                self.metric_labels['Battery Time Left'].config(text=format_time(battery.secsleft) if battery else "N/A")
                self.metric_labels['Process Count'].config(text=f"{processes}")
                self.metric_labels['Thread Count'].config(text=f"{threads}")
                self.metric_labels['Handles Count'].config(text=f"{handles}")
                self.metric_labels['System Uptime'].config(text=format_time(uptime))
                self.metric_labels['Boot Time'].config(text=format_datetime(boot_time))
                self.metric_labels['Load Average 1m'].config(text=f"{load_avg[0]}")
                self.metric_labels['Load Average 5m'].config(text=f"{load_avg[1]}")
                self.metric_labels['Load Average 15m'].config(text=f"{load_avg[2]}")
                self.metric_labels['Context Switches'].config(text=f"{ctx_switches}")
                self.metric_labels['Interrupts'].config(text=f"{interrupts}")
                self.metric_labels['Soft Interrupts'].config(text=f"{soft_interrupts}")
                self.metric_labels['Syscalls'].config(text=f"{syscalls}")
                self.metric_labels['GPU Usage'].config(text=f"{gpu_metrics['gpu_usage']}%")
                self.metric_labels['GPU Memory Total'].config(text=format_bytes(gpu_metrics['memory_total']))
                self.metric_labels['GPU Memory Used'].config(text=format_bytes(gpu_metrics['memory_used']))
                self.metric_labels['GPU Memory Free'].config(text=format_bytes(gpu_metrics['memory_free']))
                self.metric_labels['GPU Temperature'].config(text=f"{gpu_metrics['temperature']}°C")

                # Fetch agent metrics from AgentMonitor
                agent_metrics = self.agent_monitor.get_agent_metrics()

                # Update agent metric labels
                for metric, value in agent_metrics.items():
                    if metric in self.metric_labels:
                        self.metric_labels[metric].config(text=value)

                self.logger.info("Metrics display updated successfully.")
        except Exception as e:
            self.logger.error(f"Error updating metrics display: {e}", exc_info=True)
            raise

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

    def _get_system_uptime(self):
        """
        Calculates the system uptime.
        """
        try:
            uptime_seconds = psutil.boot_time()
            import time
            current_time = time.time()
            return current_time - uptime_seconds
        except Exception as e:
            self.logger.error(f"Error calculating system uptime: {e}", exc_info=True)
            return 0

    def _get_handles_count(self):
        """
        Retrieves the total number of file handles.
        """
        try:
            if hasattr(psutil.Process, 'num_handles'):
                total_handles = sum(p.num_handles() for p in psutil.process_iter())
                return total_handles
            else:
                return 'N/A'
        except Exception as e:
            self.logger.error(f"Error getting handles count: {e}", exc_info=True)
            return 'N/A'

    def _get_gpu_metrics(self):
        """
        Retrieves GPU usage metrics.
        """
        try:
            gpu_metrics = {
                'gpu_usage': 'N/A',
                'memory_total': 0,
                'memory_used': 0,
                'memory_free': 0,
                'temperature': 'N/A'
            }
            try:
                import GPUtil
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu = gpus[0]
                    gpu_metrics['gpu_usage'] = gpu.load * 100
                    gpu_metrics['memory_total'] = gpu.memoryTotal * 1024 * 1024
                    gpu_metrics['memory_used'] = gpu.memoryUsed * 1024 * 1024
                    gpu_metrics['memory_free'] = gpu.memoryFree * 1024 * 1024
                    gpu_metrics['temperature'] = gpu.temperature
            except ImportError:
                self.logger.warning("GPUtil module not found. GPU metrics will not be available.")
            return gpu_metrics
        except Exception as e:
            self.logger.error(f"Error getting GPU metrics: {e}", exc_info=True)
            return {
                'gpu_usage': 'N/A',
                'memory_total': 0,
                'memory_used': 0,
                'memory_free': 0,
                'temperature': 'N/A'
            }
