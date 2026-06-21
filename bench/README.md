# TonIO benchmarks

Run at: Sun 21 Jun 2026, 15:45    
Environment: AMD Ryzen 7 5700X @ Gentoo Linux 6.12.91 (CPUs: 16)    
Python version: 3.14    
TonIO version: 0.7.0    

### Running 1 million coroutines

Time to run 1 million coroutines (lower is better).


| Runtime | Creation time | Exec time | Total time | Relative performance |
| --- | --- | --- | --- | --- |
| TonIO yield | 111.23ms | 443.56ms | 554.79ms | 5.28x |
| TonIO async | 83.87ms | 822.008ms | 905.878ms | 3.24x |
| TonIO yield (context) | 74.046ms | 640.698ms | 714.745ms | 4.1x |
| TonIO async (context) | 52.003ms | 941.271ms | 993.273ms | 2.95x |
| AsyncIO | 38.968ms | 2892.167ms | 2931.135ms | 1.0x |
| Trio | 2775.391ms | 5218.768ms | 7994.159ms | 0.37x |
| TinyIO | 73.462ms | 3323.825ms | 3397.288ms | 0.86x |

### Sockets

TCP echo server with raw sockets comparison using 1KB, 10KB and 100KB messages.


| Runtime | Throughput (1KB) | Throughput (10KB) | Throughput (100KB) |
| --- | --- | --- | --- |
| TonIO yield | 113010.2 (2.02x) | 95657.5 (1.97x) | 40865.7 (1.58x) | 
| TonIO async | 117470.7 (2.1x) | 94983.4 (1.95x) | 42168.3 (1.63x) | 
| TonIO yield (context) | 112300.5 (2.01x) | 95049.1 (1.96x) | 39599.0 (1.53x) | 
| TonIO async (context) | 116522.3 (2.09x) | 97953.1 (2.01x) | 41552.2 (1.61x) | 
| AsyncIO | 55809.5 (1.0x) | 48612.4 (1.0x) | 25810.0 (1.0x) | 
| Trio | 80954.7 (1.45x) | 67240.0 (1.38x) | 32996.5 (1.28x) | 

#### 1KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 1130102 | 113010.2 (2.02x) | 0.032ms | 0.05ms | 0.005 |
| TonIO async | 1174707 | 117470.7 (2.1x) | 0.031ms | 0.048ms | 0.003 |
| TonIO yield (context) | 1123005 | 112300.5 (2.01x) | 0.032ms | 0.049ms | 0.004 |
| TonIO async (context) | 1165223 | 116522.3 (2.09x) | 0.031ms | 0.048ms | 0.005 |
| AsyncIO | 558095 | 55809.5 (1.0x) | 0.07ms | 0.085ms | 0.003 |
| Trio | 809547 | 80954.7 (1.45x) | 0.048ms | 0.072ms | 0.009 |


#### 10KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 956575 | 95657.5 (1.97x) | 0.04ms | 0.051ms | 0.002 |
| TonIO async | 949834 | 94983.4 (1.95x) | 0.041ms | 0.057ms | 0.005 |
| TonIO yield (context) | 950491 | 95049.1 (1.96x) | 0.04ms | 0.054ms | 0.002 |
| TonIO async (context) | 979531 | 97953.1 (2.01x) | 0.04ms | 0.05ms | 0.002 |
| AsyncIO | 486124 | 48612.4 (1.0x) | 0.08ms | 0.096ms | 0.003 |
| Trio | 672400 | 67240.0 (1.38x) | 0.058ms | 0.088ms | 0.012 |


#### 100KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 408657 | 40865.7 (1.58x) | 0.096ms | 0.112ms | 0.006 |
| TonIO async | 421683 | 42168.3 (1.63x) | 0.093ms | 0.11ms | 0.007 |
| TonIO yield (context) | 395990 | 39599.0 (1.53x) | 0.098ms | 0.119ms | 0.007 |
| TonIO async (context) | 415522 | 41552.2 (1.61x) | 0.095ms | 0.11ms | 0.006 |
| AsyncIO | 258100 | 25810.0 (1.0x) | 0.153ms | 0.177ms | 0.009 |
| Trio | 329965 | 32996.5 (1.28x) | 0.119ms | 0.174ms | 0.024 |


### Concurrency

#### 1 million coros


| Mode | Threads | Total time |
| --- | --- | --- |
| TonIO yield | 1 | 558.969ms |
| TonIO async | 1 | 923.64ms |
| TonIO yield | 2 | 750.54ms |
| TonIO async | 2 | 921.591ms |
| TonIO yield | 4 | 1010.457ms |
| TonIO async | 4 | 925.082ms |
| TonIO yield | 8 | 1228.469ms |
| TonIO async | 8 | 1140.847ms |

#### Sockets


| Mode | Threads | Throughput (10KB) |
| --- | --- | --- |
| TonIO yield | 1 | 97512.2 |
| TonIO async | 1 | 99118.6 |
| TonIO yield | 2 | 162615.3 |
| TonIO async | 2 | 168287.6 |
| TonIO yield | 4 | 232004.2 |
| TonIO async | 4 | 237844.6 |
| TonIO yield | 8 | 291462.0 |
| TonIO async | 8 | 301361.3 |
