# TonIO benchmarks

Run at: Fri 01 May 2026, 09:05    
Environment: AMD Ryzen 7 5700X @ Gentoo Linux 6.12.77 (CPUs: 16)    
Python version: 3.14    
TonIO version: 0.5.0    

### Running 1 million coroutines

Time to run 1 million coroutines (lower is better).


| Runtime | Creation time | Exec time | Total time |
| --- | --- | --- | --- |
| TonIO yield | 106.067ms | 702.708ms | 808.776ms (3.62x) |
| TonIO async | 50.173ms | 1002.547ms | 1052.72ms (2.78x) |
| TonIO yield (context) | 50.084ms | 879.15ms | 929.234ms (3.15x) |
| TonIO async (context) | 85.584ms | 1133.919ms | 1219.503ms (2.4x) |
| AsyncIO | 39.147ms | 2891.652ms | 2930.799ms (1.0x) |
| Trio | 2612.054ms | 5833.652ms | 8445.706ms (0.35x) |
| TinyIO | 73.112ms | 3371.104ms | 3444.215ms (0.85x) |

### Sockets

TCP echo server with raw sockets comparison using 1KB, 10KB and 100KB messages.


| Runtime | Throughput (1KB) | Throughput (10KB) | Throughput (100KB) |
| --- | --- | --- | --- |
| TonIO yield | 151442.0 (2.67x) | 135209.7 (2.67x) | 47362.0 (1.68x) | 
| TonIO async | 118100.8 (2.08x) | 99069.6 (1.96x) | 41850.1 (1.49x) | 
| TonIO yield (context) | 152652.6 (2.69x) | 135013.5 (2.67x) | 46667.6 (1.66x) | 
| TonIO async (context) | 117499.9 (2.07x) | 98994.2 (1.96x) | 40926.3 (1.45x) | 
| AsyncIO | 56783.4 (1.0x) | 50600.9 (1.0x) | 28153.1 (1.0x) | 
| Trio | 82806.3 (1.46x) | 72285.8 (1.43x) | 35344.2 (1.26x) | 

#### 1KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 1514420 | 151442.0 (2.67x) | 0.023ms | 0.045ms | 0.006 |
| TonIO async | 1181008 | 118100.8 (2.08x) | 0.031ms | 0.046ms | 0.002 |
| TonIO yield (context) | 1526526 | 152652.6 (2.69x) | 0.023ms | 0.044ms | 0.005 |
| TonIO async (context) | 1174999 | 117499.9 (2.07x) | 0.031ms | 0.048ms | 0.007 |
| AsyncIO | 567834 | 56783.4 (1.0x) | 0.07ms | 0.083ms | 0.003 |
| Trio | 828063 | 82806.3 (1.46x) | 0.046ms | 0.07ms | 0.009 |


#### 10KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 1352097 | 135209.7 (2.67x) | 0.03ms | 0.042ms | 0.002 |
| TonIO async | 990696 | 99069.6 (1.96x) | 0.04ms | 0.05ms | 0.002 |
| TonIO yield (context) | 1350135 | 135013.5 (2.67x) | 0.03ms | 0.042ms | 0.002 |
| TonIO async (context) | 989942 | 98994.2 (1.96x) | 0.04ms | 0.05ms | 0.002 |
| AsyncIO | 506009 | 50600.9 (1.0x) | 0.08ms | 0.09ms | 0.003 |
| Trio | 722858 | 72285.8 (1.43x) | 0.054ms | 0.079ms | 0.011 |


#### 100KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 473620 | 47362.0 (1.68x) | 0.082ms | 0.12ms | 0.009 |
| TonIO async | 418501 | 41850.1 (1.49x) | 0.094ms | 0.11ms | 0.005 |
| TonIO yield (context) | 466676 | 46667.6 (1.66x) | 0.083ms | 0.109ms | 0.008 |
| TonIO async (context) | 409263 | 40926.3 (1.45x) | 0.096ms | 0.113ms | 0.006 |
| AsyncIO | 281531 | 28153.1 (1.0x) | 0.139ms | 0.165ms | 0.008 |
| Trio | 353442 | 35344.2 (1.26x) | 0.111ms | 0.159ms | 0.022 |


### Concurrency

#### 1 million coros


| Mode | Threads | Total time |
| --- | --- | --- |
| TonIO yield | 1 | 801.614ms |
| TonIO async | 1 | 1055.756ms |
| TonIO yield | 2 | 996.529ms |
| TonIO async | 2 | 1084.459ms |
| TonIO yield | 4 | 933.584ms |
| TonIO async | 4 | 1072.093ms |
| TonIO yield | 8 | 1864.9ms |
| TonIO async | 8 | 1364.733ms |

#### Sockets


| Mode | Threads | Throughput (10KB) |
| --- | --- | --- |
| TonIO yield | 1 | 136119.0 |
| TonIO async | 1 | 95311.0 |
| TonIO yield | 2 | 141497.3 |
| TonIO async | 2 | 154699.5 |
| TonIO yield | 4 | 131113.1 |
| TonIO async | 4 | 140055.0 |
| TonIO yield | 8 | 100390.3 |
| TonIO async | 8 | 125320.1 |
