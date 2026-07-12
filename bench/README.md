# TonIO benchmarks

Run at: Sun 12 Jul 2026, 13:40    
Environment: AMD Ryzen 7 5700X @ Gentoo Linux 6.12.93 (CPUs: 16)    
Python version: 3.14    
TonIO version: 0.8.2    

### Running 1 million coroutines

Time to run 1 million coroutines (lower is better).


| Runtime | Creation time | Exec time | Total time | Relative performance |
| --- | --- | --- | --- | --- |
| TonIO yield | 112.109ms | 448.233ms | 560.342ms | 5.18x |
| TonIO async | 84.707ms | 788.682ms | 873.389ms | 3.32x |
| TonIO yield (context) | 71.866ms | 645.002ms | 716.869ms | 4.05x |
| TonIO async (context) | 51.756ms | 926.25ms | 978.006ms | 2.97x |
| AsyncIO | 40.371ms | 2860.729ms | 2901.1ms | 1.0x |
| Trio | 2227.65ms | 5241.881ms | 7469.531ms | 0.39x |
| TinyIO | 70.015ms | 3369.423ms | 3439.438ms | 0.84x |

### Sockets

TCP echo server with raw sockets comparison using 1KB, 10KB and 100KB messages.


| Runtime | Throughput (1KB) | Throughput (10KB) | Throughput (100KB) |
| --- | --- | --- | --- |
| TonIO yield | 127575.7 (2.37x) | 107360.6 (2.24x) | 44795.5 (1.6x) | 
| TonIO async | 134070.3 (2.49x) | 109253.5 (2.28x) | 43632.7 (1.56x) | 
| TonIO yield (context) | 124513.7 (2.31x) | 106177.1 (2.22x) | 43509.3 (1.56x) | 
| TonIO async (context) | 127584.6 (2.37x) | 106695.0 (2.23x) | 45045.6 (1.61x) | 
| AsyncIO | 53800.8 (1.0x) | 47837.7 (1.0x) | 27913.1 (1.0x) | 
| Trio | 78184.1 (1.45x) | 68836.0 (1.44x) | 33610.1 (1.2x) | 

#### 1KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 1275757 | 127575.7 (2.37x) | 0.03ms | 0.04ms | 0.001 |
| TonIO async | 1340703 | 134070.3 (2.49x) | 0.03ms | 0.04ms | 0.002 |
| TonIO yield (context) | 1245137 | 124513.7 (2.31x) | 0.03ms | 0.04ms | 0.001 |
| TonIO async (context) | 1275846 | 127584.6 (2.37x) | 0.03ms | 0.042ms | 0.002 |
| AsyncIO | 538008 | 53800.8 (1.0x) | 0.071ms | 0.095ms | 0.005 |
| Trio | 781841 | 78184.1 (1.45x) | 0.051ms | 0.077ms | 0.01 |


#### 10KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 1073606 | 107360.6 (2.24x) | 0.039ms | 0.05ms | 0.004 |
| TonIO async | 1092535 | 109253.5 (2.28x) | 0.035ms | 0.05ms | 0.006 |
| TonIO yield (context) | 1061771 | 106177.1 (2.22x) | 0.04ms | 0.05ms | 0.002 |
| TonIO async (context) | 1066950 | 106695.0 (2.23x) | 0.037ms | 0.05ms | 0.005 |
| AsyncIO | 478377 | 47837.7 (1.0x) | 0.082ms | 0.102ms | 0.005 |
| Trio | 688360 | 68836.0 (1.44x) | 0.056ms | 0.085ms | 0.011 |


#### 100KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 447955 | 44795.5 (1.6x) | 0.09ms | 0.103ms | 0.004 |
| TonIO async | 436327 | 43632.7 (1.56x) | 0.09ms | 0.108ms | 0.004 |
| TonIO yield (context) | 435093 | 43509.3 (1.56x) | 0.091ms | 0.108ms | 0.004 |
| TonIO async (context) | 450456 | 45045.6 (1.61x) | 0.089ms | 0.1ms | 0.004 |
| AsyncIO | 279131 | 27913.1 (1.0x) | 0.141ms | 0.167ms | 0.01 |
| Trio | 336101 | 33610.1 (1.2x) | 0.117ms | 0.168ms | 0.023 |


### Concurrency

#### 1 million coros


| Mode | Threads | Total time |
| --- | --- | --- |
| TonIO yield | 1 | 577.176ms |
| TonIO async | 1 | 876.986ms |
| TonIO yield | 2 | 747.713ms |
| TonIO async | 2 | 903.686ms |
| TonIO yield | 4 | 1039.288ms |
| TonIO async | 4 | 924.032ms |
| TonIO yield | 8 | 1281.226ms |
| TonIO async | 8 | 1049.043ms |

#### Sockets


| Mode | Threads | Throughput (10KB) |
| --- | --- | --- |
| TonIO yield | 1 | 108001.2 |
| TonIO async | 1 | 110366.7 |
| TonIO yield | 2 | 180453.6 |
| TonIO async | 2 | 196350.9 |
| TonIO yield | 4 | 257195.4 |
| TonIO async | 4 | 271309.1 |
| TonIO yield | 8 | 346740.4 |
| TonIO async | 8 | 369812.7 |
