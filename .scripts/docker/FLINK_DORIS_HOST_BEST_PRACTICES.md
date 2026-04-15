# Flink / Doris 大数据组件：宿主机调优与最佳实践

本文面向在 **Linux 宿主机** 上通过 Docker Compose 部署 Flink、Doris 的场景（与仓库内 `.scripts/docker/docker-compose.yml` 一致），汇总 **操作系统参数**、**资源与磁盘**、**容器与 JVM** 等层面的常见最佳实践。生产环境请结合业务 QPS、数据量、副本数与硬件规格做压测后再定稿。

---

## 一、通用 Linux 内核与资源限制

### 1.1 虚拟内存与文件映射（Doris / JVM 均敏感）

| 参数 | 建议 | 说明 |
|------|------|------|
| `vm.max_map_count` | **≥ 2000000**（生产常见 **2000000～8388608**） | 进程内存映射段数量上限；Doris BE、Elasticsearch 等依赖较大映射空间，不足会导致启动失败或不稳定。 |
| `vm.swappiness` | **0～10**（内存充足时偏 **0**；内存紧张可 **1～10**） | 降低主动换出倾向，避免延迟抖动；完全禁用 swap 需评估 OOM 风险。 |
| `vm.overcommit_memory` | 保持默认 **0** 或按发行版文档；若明确允许过量分配可 **1** | 与 OOM 行为相关，改动前需理解业务内存模型。 |

**临时生效：**

```bash
sudo sysctl -w vm.max_map_count=2000000
sudo sysctl -w vm.swappiness=10
```

**持久化：** 在 `/etc/sysctl.d/` 下新增文件（例如 `99-easyaiot-bigdata.conf`）：

```ini
vm.max_map_count = 2000000
vm.swappiness = 10
```

执行 `sudo sysctl --system` 或重启后生效。

官方参考：[Linux 部署环境检查（Doris）](https://doris.apache.org/docs/install/preparation/os-checking/)

### 1.2 透明大页（Transparent Huge Pages, THP）

THP 可能导致 **GC 停顿变长**、**延迟毛刺**。大数据场景普遍建议关闭。

```bash
# 临时关闭
echo never | sudo tee /sys/kernel/mm/transparent_hugepage/enabled
echo never | sudo tee /sys/kernel/mm/transparent_hugepage/defrag
```

**持久化：** 使用 `systemd-tmpfiles`、`rc.local` 或发行版推荐方式在开机时写入上述值；部分环境需在 GRUB 内核参数中禁用。

### 1.3 文件句柄与进程数（ulimit）

容器内进程仍受 **宿主机 cgroup 与 Docker 默认限制** 影响，建议在宿主机对运行 Docker 的用户或 `docker` 服务调大：

| 项 | 建议 |
|----|------|
| `nofile`（打开文件数） | **≥ 655350**（生产可更高，如 **1048576**） |
| `nproc` | 按并发任务数评估，一般 **≥ 65535** |

**示例（`/etc/security/limits.d/99-bigdata.conf`）：**

```text
* soft nofile 1048576
* hard nofile 1048576
* soft nproc 65535
* hard nproc 65535
```

修改后需 **重新登录** 或重启相关服务。若通过 `systemd` 管理 Docker，可能还需在 `docker.service` 的 `LimitNOFILE=` 中提高上限。

### 1.4 网络（高吞吐流式 / 查询场景）

| 参数 | 方向 | 说明 |
|------|------|------|
| `net.core.somaxconn` | 适当增大 |  accept 队列，高并发连接时有益。 |
| `net.ipv4.tcp_max_syn_backlog` | 适当增大 | SYN 队列。 |
| `net.ipv4.ip_local_port_range` | 扩大可用临时端口范围 | 大量对外连接时减少端口耗尽。 |

具体数值与业务连接模型相关，建议在测试环境用 `ss`、`sar` 观察后再调。

---

## 二、Doris 宿主机专项

### 2.1 必做项小结

1. **`vm.max_map_count` 足够大**（见上文）。  
2. **关闭 THP**（见上文）。  
3. **数据盘**：优先 **XFS** 或成熟生产验证过的 **ext4**；避免将数据目录放在高延迟或共享型网络盘上（除非明确按 NAS/对象存储架构设计）。  
4. **CPU 调度**：独占或绑核可减少噪声邻居；Kubernetes 下常结合 `cpu-manager-policy=static` 等，物理机可结合 `taskset` / cgroup v2。  
5. **时钟**：FE/BE 多节点时 **NTP/chrony** 同步，避免元数据与时间相关逻辑异常。

### 2.2 磁盘与 I/O

- **FE 元数据**、**BE 存储**分盘部署更佳：元数据盘与数据盘分离，降低相互 I/O 干扰。  
- 监控 **`iowait`**、**磁盘队列深度**、**fsync 延迟**；Doris 导入与 compaction 对磁盘写放大明显。  
- Docker 场景下 bind mount 到本地盘优于将高写入目录放在默认 Docker 存储驱动层叠文件系统上（视实际存储驱动而定）。

### 2.3 内存

- BE 会占用大量 **page cache** 与堆外内存；宿主机预留 **操作系统 + 其他守护进程** 内存，避免与 BE 争抢导致 OOM。  
- 生产常为 BE 配置 **独立 cgroup 内存上限** 或容器 memory limit，并与 `be.conf` 中内存相关参数一致，避免 “容器限制小于进程认为可用内存” 的不一致。

### 2.4 安全与权限

- 本仓库 Compose 中 BE 使用 **`privileged: true`** 仅为简化单机部署；生产应 **收紧权限**，用 `cap_add`、`sysctls` 等替代全特权，并遵循 [Doris 官方部署文档](https://doris.apache.org/docs/gettingStarted/quick-start/) 的安全建议。

---

## 三、Flink 宿主机专项

### 3.1 CPU 与 NUMA

- **TaskManager 线程数** 与 **slot 数** 不要超过物理核上的合理并发，否则上下文切换开销上升。  
- **NUMA 机器**：尽量让 JVM 堆与网络中断落在同一 NUMA 节点（绑核、`numactl` 等），可降低跨节点访问延迟。

### 3.2 网络与 Checkpoint

- **Checkpoint 到对象存储 / HDFS** 时，注意 **带宽与连接数**；适当调大 `net.*` 与 ulimit（见第一节）。  
- 高反压场景下，除 Flink 参数外，需排查 **下游系统**（Kafka、Doris、JDBC 等）与 **宿主机网络** 是否成为瓶颈。

### 3.3 磁盘

- **RocksDB state**、**本地临时目录**、**日志** 建议放在 **低延迟、高 IOPS** 的本地盘。  
- 将 `high-io` 与 `checkpoint` 目录分离到不同磁盘，可减少相互干扰。

### 3.4 容器内 JVM

- JobManager / TaskManager 的 **堆与托管内存** 需在 `flink-conf.yaml` 或环境变量中与 **容器 memory limit** 对齐，并预留 **堆外**（网络、RocksDB、元空间等）。  
- 官方文档：[Flink on Docker](https://nightlies.apache.org/flink/flink-docs-stable/docs/deployment/resource-providers/standalone/docker/)

---

## 四、Docker 与 Compose 层面

1. **日志**：配置 `json-file` 的 `max-size`、`max-file`，避免 Flink/Doris 日志打满根分区。  
2. **重启策略**：生产可结合健康检查与编排层重启策略，避免无限重启掩盖根因。  
3. **资源上限**：为 FE/BE/JM/TM 设置 **`cpus` / `mem_limit`**（或迁移到 Kubernetes 的 request/limit），与 JVM 和 Doris 内存参数一致。  
4. **时区与编码**：与业务一致设置 `TZ`、`LANG`，减少日志与调度时间歧义。

---

## 五、验证与监控清单（建议）

| 检查项 | 命令或方式 |
|--------|------------|
| `vm.max_map_count` | `sysctl vm.max_map_count` |
| THP 状态 | `cat /sys/kernel/mm/transparent_hugepage/enabled` |
| 文件句柄 | `ulimit -n`（注意用户与 systemd 服务上下文） |
| 磁盘延迟与利用率 | `iostat -xz 1`、`pidstat -d` |
| 内存与 swap | `free -h`、`vmstat 1` |
| Doris | FE/BE HTTP 端口、导入与查询 P99、compaction 队列 |
| Flink | Web UI **Backpressure**、Checkpoint 时长与失败率、GC 日志 |

---

## 六、与本仓库脚本的对应关系

- 中间件目录：`.scripts/docker/flink_data/`、`.scripts/docker/doris_data/`（由 `install_middleware_linux.sh` 创建）。  
- 部署前建议在目标宿主机完成 **第一节 + 第二节 2.1** 的配置，再执行安装脚本。  
- 若 Doris 镜像为 **x86_64** 而宿主机为 **ARM**，需更换镜像标签或 `platform`，并重新验证上述内核参数在 ARM 发行版上的等价项。

---

## 七、延伸阅读（官方文档）

- Apache Flink：[Deployment / Docker](https://nightlies.apache.org/flink/flink-docs-stable/docs/deployment/resource-providers/standalone/docker/)  
- Apache Doris：[OS 检查与参数](https://doris.apache.org/docs/install/preparation/os-checking/)、[集群部署总览](https://doris.apache.org/docs/install/cluster-deployment/)

*文档版本与仓库中间件编排同步维护；参数以官方最新版本文档为准。*
