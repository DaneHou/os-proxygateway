# os-proxygateway 设计评估与执行计划

**基于:** `opnsense-multi-proxy-gateway-design.md`
**评估日期:** 2026-02-23
**目标:** 评估实用性、影响力、可行性、拓展性，并制定可执行计划

---

## 一、设计总结

核心思路：在 OPNsense 上将远程 SOCKS5/HTTP 代理包装为标准网关接口（tun 设备），让用户通过防火墙规则将特定设备或子网的流量透明地路由到不同的代理服务器，无需客户端任何配置。

---

## 二、实用性评估 (Practicality) — 评分: ★★★★☆ (4/5)

### 真实痛点

| 场景 | 当前方案 | 痛点 |
|------|---------|------|
| 不同设备走不同代理 | 每台设备手动配置代理 | 繁琐、IoT 设备无法配置 |
| 流媒体设备解锁地区限制 | 需要全局 VPN 或路由器刷固件 | VPN 对所有流量生效，不够灵活 |
| 访客网络走审计代理 | 手动 iptables/pf 规则 + redsocks | 配置复杂，重启丢失 |
| 多出口冗余 | 多 WAN + 策略路由 | 代理场景不适用，只支持直连 |

**结论：** 这些都是网络管理员在实际部署中遇到的真实问题。OPNsense 原生支持 VPN-as-gateway（OpenVPN、WireGuard），但完全没有 proxy-as-gateway 的能力，这是一个明确的功能空白。

### 实用性优势

1. **零客户端配置** — 路由层透明转发，设备不需要知道代理的存在
2. **复用现有基础设施** — 很多用户已经有 SOCKS5/HTTP 代理（如 SSH tunnel、Shadowsocks、商业代理），但没有好的方式将其作为网关使用
3. **与 OPNsense 原生功能无缝集成** — 注册为标准网关后，可以直接利用防火墙规则、Gateway Group（failover/load-balance）、策略路由等已有功能

### 实用性风险

| 风险 | 严重性 | 缓解措施 |
|------|--------|---------|
| tun2socks 引入 userland 性能开销 | 中 | 目标场景不是高吞吐（家庭/小型办公），百兆级别足够 |
| HTTP 代理不支持 UDP | 中 | 文档明确说明限制；SOCKS5 模式支持 UDP |
| 代理服务器不稳定导致网络中断 | 中 | Health check + kill switch + gateway group failover |
| 用户技术门槛：需理解路由/网关概念 | 低 | UI 设计足够直觉化，且目标用户是 OPNsense 使用者（已有网络基础） |

---

## 三、影响力评估 (Impact) — 评分: ★★★★☆ (4/5)

### 市场空白分析

目前在 OPNsense/pfSense 生态中，**没有**成熟的 proxy-as-gateway 插件：

| 现有方案 | 问题 |
|---------|------|
| pfSense 社区的 redsocks 教程 | 手动配置 pf 规则，仅 TCP，无 GUI，无法注册为网关 |
| Clash/sing-box on Linux router | Linux 生态，不适用 BSD/OPNsense |
| Proxychains | 单应用级别，非网络级 |
| 商业 SD-WAN 方案 | 价格高，不开源 |

**这个插件将是 OPNsense 生态中第一个实现 proxy-as-gateway 的原生插件。**

### 潜在用户群

1. **隐私/安全爱好者** — OPNsense 核心用户群，需要精细化流量控制
2. **小型企业网络管理员** — 多出口、多供应商代理场景
3. **海外用户 / 远程工作者** — 需要地域化路由（如流媒体解锁）
4. **IoT 安全场景** — 将不可信设备流量强制走审计代理

### 社区影响

- OPNsense 社区论坛中 "proxy as gateway" 相关讨论长期存在但没有解决方案
- 如果插件进入官方 plugin 仓库，能显著提升 OPNsense 相比 pfSense 的功能优势
- 该功能填补了 VPN gateway 和 直连 之间的空白，是 OPNsense 路由能力的自然延伸

### 影响力风险

| 风险 | 评估 |
|------|------|
| 用户基数可能不大（小众需求） | OPNsense 本身是小众产品，但其用户质量高、社区活跃，代理网关是高需求功能 |
| 与 VPN 方案竞争 | 不竞争，互补。VPN 需要服务端，代理不需要；很多用户同时使用两者 |
| GPL-3.0 许可证（tun2socks）可能阻碍进入官方仓库 | 需验证 OPNsense 对 GPL 依赖的政策；可考虑将 tun2socks 作为独立包 |

---

## 四、可行性评估 (Feasibility) — 评分: ★★★☆☆ (3.5/5)

### 技术可行性分析

#### ✅ 确定可行的部分

| 组件 | 依据 |
|------|------|
| tun2socks 在 FreeBSD 上运行 | Go 的 `golang.org/x/net` 和 gVisor netstack 支持 FreeBSD tun 设备；tun2socks v2 有 FreeBSD 编译目标 |
| OPNsense MVC 插件开发 | 框架成熟，大量第三方插件（os-wireguard、os-haproxy 等）可作参考 |
| tun 设备创建和路由 | FreeBSD 原生支持 `ifconfig tunN create`，OPNsense 的 WireGuard 插件已经用了类似模式 |
| configd action 定义 | 标准 OPNsense 模式，文档清晰 |
| pf NAT 规则生成 | OPNsense 有 API 和 configd 支持动态规则 |

#### ⚠️ 需要验证的部分（关键风险）

| 问题 | 风险 | 解决路径 |
|------|------|---------|
| **tun2socks 在 OPNsense 特定内核上的兼容性** | 高 | Phase 1 第一步就应该在真实 OPNsense 上编译测试 tun2socks |
| **动态网关注册** | 高 | OPNsense 的网关注册依赖 `config.xml` + `dpinger`，运行时动态添加可能需要 `configctl interface routes reconfigure`；需要实验确认是否可以不做全量 reload |
| **FreeBSD tun 设备在 tun2socks 下的性能** | 中 | 需要在目标硬件上做 iperf 基准测试，确认 userland 开销是否可接受 |
| **DNS 泄露防护的 pf 规则复杂度** | 中 | 多实例时 pf 规则可能变得复杂，需要仔细设计规则生成逻辑 |
| **tun2socks 进程稳定性** | 中 | 长时间运行是否有内存泄漏？需要 stress test；可用 rc.d 的 restart 机制兜底 |

#### ❌ 已知限制

| 限制 | 影响 | 对策 |
|------|------|------|
| HTTP 代理不支持 UDP | DNS 和 UDP 流量无法通过 HTTP 代理 | 文档说明；推荐使用 SOCKS5；可选 DNS-over-HTTPS 方案 |
| userland 转发有性能上限 | 不适合 Gbps 级别高吞吐场景 | 目标定位家庭/小型办公，100-500Mbps 足够 |
| GPL-3.0 (tun2socks) | 可能影响分发方式 | 将 tun2socks 作为独立 pkg 安装，插件本身用 BSD 许可 |

### 开发能力要求

| 技能 | 必要性 | 难度 |
|------|--------|------|
| PHP (OPNsense MVC) | 必须 | 中 — 有大量现有插件可参考 |
| FreeBSD 网络管理 (ifconfig, pf, routing) | 必须 | 中高 — 需要较深的 BSD 网络知识 |
| Go (编译 tun2socks) | 交叉编译即可 | 低 — 只需编译，不需修改源码 |
| Python (gateway 注册脚本) | 必须 | 低 |
| Shell scripting (setup/teardown) | 必须 | 低 |
| OPNsense configd 和 API 框架 | 必须 | 中 — 需要阅读文档和参考代码 |

---

## 五、拓展性评估 (Extensibility) — 评分: ★★★★★ (5/5)

设计文档在拓展性方面做得很好。架构上的 "每个代理连接 = tun + 进程 + 网关" 模式是高度模块化的。

### 已规划的扩展方向

| 方向 | 可行性 | 价值 |
|------|--------|------|
| 代理链（proxy chaining） | 高 — tun2socks 支持链式代理 | 高级隐私场景 |
| 负载均衡 | 高 — OPNsense Gateway Group 原生支持 | 提高可靠性 |
| PAC 文件生成 | 高 — 纯逻辑实现 | 混合部署场景 |
| ARM64 支持 | 高 — Go 交叉编译 | Raspberry Pi / ARM 路由器 |
| 带宽监控 | 中 — 需要读取 tun 设备统计 | 运维可观测性 |
| Unbound DNS 集成 | 中 — 需要修改 Unbound 配置 | 更精细的 DNS 控制 |

### 未规划但有潜力的扩展

| 方向 | 说明 |
|------|------|
| **WireGuard over proxy** | 将 WireGuard 流量通过代理传输，适用于代理是唯一出口的场景 |
| **API-driven proxy 管理** | 暴露 REST API 让外部系统动态添加/删除代理连接 |
| **代理订阅支持** | 导入代理订阅链接（如 Clash 格式），自动创建多个连接 |
| **流量统计 + Grafana 集成** | 导出 Prometheus 指标，可视化每个代理隧道的流量 |
| **IPv6 支持** | tun2socks 支持 IPv6，可扩展数据模型 |
| **容器化 tun2socks** | 使用 FreeBSD jail 隔离每个 tun2socks 实例 |

### 架构拓展性评估

设计的核心模式 `proxy connection → tun interface → OPNsense gateway` 是高度解耦的：

- **新增代理协议** — 只需 tun2socks 支持（或替换为其他引擎如 sing-box），上层不变
- **新增功能** — OPNsense MVC 框架允许自然地扩展 model/controller/view
- **水平扩展** — 每个连接独立，互不影响，理论上只受系统资源限制
- **替换核心引擎** — 如果 tun2socks 不满足需求，可以切换到 sing-box、hev-socks5-tunnel 等，接口层不变

---

## 六、综合评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 实用性 | ★★★★☆ | 解决真实痛点，目标场景明确 |
| 影响力 | ★★★★☆ | 填补 OPNsense 生态空白，用户群虽小众但需求强 |
| 可行性 | ★★★½☆ | 技术路径清晰但有关键风险需验证（tun2socks 兼容性、网关注册） |
| 拓展性 | ★★★★★ | 模块化设计，扩展空间大 |
| **综合** | **★★★★☆** | **值得投入，但需要先做技术验证（PoC）来降低风险** |

### 核心建议

**先做 PoC（Proof of Concept），再做插件。** 不要直接进入 OPNsense MVC 开发，先在一台真实的 OPNsense 机器上手动验证核心流程能跑通。

---

## 七、可执行计划

### Phase 0: 技术验证 (PoC) — 最关键

> **目标：** 在真实 OPNsense 上手动验证 tun2socks → tun 设备 → 网关注册 → 策略路由的完整链路

#### Step 0.1: 环境准备

- [ ] 准备 OPNsense 测试环境（物理机或 VirtualBox/Proxmox 虚拟机）
  - 最低：2 NIC（WAN + LAN）
  - 推荐：OPNsense 24.7+ on FreeBSD 14
- [ ] 准备一个可用的 SOCKS5 代理服务器（可以用 SSH 隧道快速搭建：`ssh -D 1080 user@remote-server`）
- [ ] 准备一台 LAN 内的测试客户端设备

#### Step 0.2: 编译 tun2socks for FreeBSD

```bash
# 在任意 Linux/Mac 开发机上交叉编译
git clone https://github.com/xjasonlyu/tun2socks.git
cd tun2socks
GOOS=freebsd GOARCH=amd64 CGO_ENABLED=0 go build -o tun2socks-freebsd-amd64 ./cmd/tun2socks

# 将二进制传到 OPNsense
scp tun2socks-freebsd-amd64 root@opnsense:/usr/local/bin/tun2socks
chmod +x /usr/local/bin/tun2socks
```

- [ ] 验证二进制能启动并输出 `--help`
- [ ] 如果编译失败，尝试备选方案：
  - `hev-socks5-tunnel` (C-based, 轻量)
  - `badvpn-tun2socks` (C-based, 经典)
  - 直接在 FreeBSD jail 里编译

#### Step 0.3: 手动创建隧道

在 OPNsense shell (SSH) 中：

```bash
# 创建 tun 设备
ifconfig tun4001 create
ifconfig tun4001 inet 172.31.1.1 172.31.1.2 mtu 1500 up

# 启动 tun2socks
/usr/local/bin/tun2socks -device tun4001 -proxy socks5://PROXY_IP:1080 &

# 添加测试路由（将 8.8.8.8 的流量走隧道）
route add 8.8.8.8/32 172.31.1.2

# 测试
ping 8.8.8.8  # 应该通过代理到达
curl --interface 172.31.1.1 http://ifconfig.me  # 应该显示代理 IP
```

- [ ] 验证流量确实经过代理
- [ ] 验证 TCP 连通性
- [ ] 验证 UDP 连通性（DNS：`dig @8.8.8.8 example.com`）

#### Step 0.4: 网关注册测试

```bash
# 方法 A：通过 OPNsense 的 config.xml 注册网关
# 编辑 /conf/config.xml，在 <gateways> 下添加：
# <gateway_item>
#   <interface>tun4001</interface>
#   <gateway>172.31.1.2</gateway>
#   <name>PROXYGW_TEST</name>
#   <descr>Test Proxy Gateway</descr>
#   <monitor_disable>0</monitor_disable>
# </gateway_item>

# 然后重新加载
configctl interface routes reconfigure

# 方法 B：使用 pluginctl / configd API
# 需要调研 OPNsense 是否有更动态的注册方式
```

- [ ] 验证网关出现在 System → Gateways
- [ ] 验证 dpinger 能监控该网关
- [ ] 在防火墙规则中选择该网关，验证策略路由生效

#### Step 0.5: 端到端测试

- [ ] 创建防火墙规则：指定测试客户端 IP → Gateway: PROXYGW_TEST
- [ ] 验证客户端所有流量都经过代理（访问 ifconfig.me 等）
- [ ] 测试 DNS 是否泄露（dnsleaktest.com）
- [ ] 测试断开代理后的行为（流量是否回落到 WAN）

**PoC 成功标准：** 一台 LAN 设备的全部流量透明地通过 SOCKS5 代理，且不需要客户端任何配置。

---

### Phase 1: MVP — Core Engine（CLI 可用）

> **目标：** 可通过 configd 命令管理多个代理网关实例

#### Step 1.1: 项目骨架搭建

```
os-proxygateway/
├── Makefile
├── pkg-descr
├── src/
│   ├── etc/inc/plugins.inc.d/
│   │   └── proxygateway.inc
│   ├── opnsense/
│   │   ├── scripts/OPNsense/ProxyGateway/
│   │   │   ├── setup.sh
│   │   │   ├── teardown.sh
│   │   │   ├── healthcheck.sh
│   │   │   └── gateway_register.py
│   │   └── service/conf/actions.d/
│   │       └── actions_proxygateway.conf
│   └── usr/local/
│       ├── bin/tun2socks
│       └── etc/rc.d/proxygateway
```

- [ ] 创建 Makefile（参考 os-wireguard 的 Makefile 格式）
- [ ] 编写 `proxygateway.inc` 注册钩子
- [ ] 编写 `rc.d/proxygateway` 服务脚本
- [ ] 编写 `actions_proxygateway.conf` (configd action 定义)

#### Step 1.2: 核心脚本开发

- [ ] `setup.sh` — 创建 tun 设备、启动 tun2socks、注册网关
  - 参数化：连接名称、代理类型、代理地址、隧道 IP
  - 自动分配 tun IP（从 172.31.0.0/16 池中）
  - PID 文件管理
- [ ] `teardown.sh` — 注销网关、停止 tun2socks、销毁 tun
- [ ] `healthcheck.sh` — 通过隧道探测远程端点
  - 成功/失败状态写入文件供网关监控读取
- [ ] `gateway_register.py` — 通过 OPNsense API/configd 注册和注销网关

#### Step 1.3: NAT 和 DNS 规则

- [ ] 自动生成 pf NAT 规则（outbound NAT on tun interface）
- [ ] DNS 泄露防护规则（阻止非隧道 DNS 流量）
- [ ] Kill-switch 规则（可选：隧道下线时丢弃流量）

#### Step 1.4: 多实例支持

- [ ] 验证同时运行 2-3 个 tun2socks 实例
- [ ] 确认 tun IP 不冲突
- [ ] 确认 pf 规则不冲突
- [ ] 确认网关独立工作

**Phase 1 交付物：**
```bash
configctl proxygateway start uswest socks5 1.2.3.4:1080
configctl proxygateway start euproxy http 5.6.7.8:8080
configctl proxygateway stop uswest
configctl proxygateway status
```

---

### Phase 2: OPNsense 集成（API + 数据模型）

> **目标：** 通过 OPNsense API 完整管理代理连接

#### Step 2.1: 数据模型

- [ ] 实现 `ProxyGateway.xml` 数据模型（按设计文档）
- [ ] 实现 `ProxyGateway.php` 模型类
- [ ] 字段验证逻辑（IP 格式、端口范围、名称唯一性）

#### Step 2.2: API 控制器

- [ ] `ConnectionController.php` — CRUD 代理连接
  - `searchItem`, `getItem`, `addItem`, `setItem`, `delItem`
- [ ] `ServiceController.php` — 启动/停止/重启服务
  - `start`, `stop`, `restart`, `status`
  - 单个连接的 start/stop
- [ ] `DiagnosticsController.php` — 诊断信息
  - `getStatus` — 所有连接的运行状态
  - `testConnection` — 测试特定代理的连通性
  - `getLogs` — 获取日志

#### Step 2.3: configd 集成

- [ ] 定义完整的 configd actions
- [ ] 实现 `reconfigure` action（读取 config → 对比运行状态 → 启动/停止变更的连接）
- [ ] 实现 service `status` 输出

#### Step 2.4: 自动化网关管理

- [ ] 连接启用时自动注册网关
- [ ] 连接禁用时自动注销网关
- [ ] 配置变更时平滑重载（不中断其他连接）

---

### Phase 3: UI 和用户体验

> **目标：** 完整的 GUI 体验，与原生 VPN 插件同级

#### Step 3.1: 主页面

- [ ] `index.volt` — 连接列表页面
  - 表格：名称、类型、服务器、状态、延迟、操作
  - 添加/编辑对话框（Tabbed: General / Proxy / Tunnel / DNS / Health / Gateway）
  - 启用/禁用/删除按钮

#### Step 3.2: 仪表板小部件

- [ ] Dashboard widget 显示所有连接状态
- [ ] 实时延迟和在线/离线状态

#### Step 3.3: 诊断页面

- [ ] 日志查看器（按实例过滤）
- [ ] 延迟图表
- [ ] "测试连接" 按钮
- [ ] 流量统计（bytes in/out）

#### Step 3.4: 文档和帮助

- [ ] 插件内帮助文本
- [ ] README / Wiki 文档

---

### Phase 4: 高级功能（按需选择）

按优先级排列：

| 优先级 | 功能 | 预期价值 |
|--------|------|---------|
| P1 | ARM64 二进制支持 | 扩大硬件兼容性 |
| P1 | Gateway Group 支持（failover） | 高可用性 |
| P2 | 代理链 | 高级隐私用户 |
| P2 | 带宽监控 + Prometheus 指标 | 可观测性 |
| P3 | PAC 文件生成 | 混合部署 |
| P3 | 代理订阅导入 | 便利性 |
| P4 | Unbound DNS 集成 | 精细 DNS 控制 |

---

## 八、风险缓解矩阵

| 风险 | 概率 | 影响 | 缓解措施 | 发现时机 |
|------|------|------|---------|---------|
| tun2socks 在 OPNsense 内核上不工作 | 中 | 致命 | Phase 0 立即验证；准备备选方案（hev-socks5-tunnel, badvpn） | PoC |
| 动态网关注册需要全量 reload | 高 | 高 | 研究 WireGuard 插件如何注册网关，模仿其方式 | PoC |
| 多实例 pf 规则冲突 | 低 | 高 | 使用 pf anchor 机制隔离每个实例的规则 | Phase 1 |
| GPL-3.0 不被 OPNsense 接受 | 中 | 中 | tun2socks 作为独立 pkg；插件本身用 BSD 许可 | Phase 2 |
| 性能不足 | 低 | 中 | PoC 中做性能基准测试；目标 100Mbps+  | PoC |
| OPNsense 大版本升级 API 变更 | 低 | 中 | 跟踪 OPNsense release notes；MVC 框架相对稳定 | 持续 |

---

## 九、建议的技术决策

### 1. 核心引擎选择

**建议：tun2socks v2 为主，hev-socks5-tunnel 为备选。**

- tun2socks v2 (Go): 功能全面，支持 SOCKS5/HTTP/SOCKS5+TLS，单二进制，Go 交叉编译方便
- hev-socks5-tunnel (C): 更轻量，纯 C 实现，FreeBSD 兼容性可能更好，但只支持 SOCKS5
- 如果 PoC 阶段 tun2socks 在 FreeBSD 上有问题，立即切换到 hev-socks5-tunnel

### 2. 网关注册方式

**建议：参考 os-wireguard 插件的实现方式。**

WireGuard 插件也需要动态创建接口和注册网关，它的做法值得直接参考。具体路径：
- 研究 `opnsense/plugins` 仓库中 `net/wireguard` 的 `gateway_register` 逻辑
- 使用 `configctl interface routes reconfigure` 触发网关刷新

### 3. 许可证策略

**建议：插件代码用 BSD-2-Clause，tun2socks 作为 runtime dependency。**

```
os-proxygateway (BSD-2-Clause)
  └── depends on: tun2socks (GPL-3.0, separate package)
```

### 4. 开发/测试环境

**建议：使用 Proxmox 虚拟化 OPNsense 进行开发测试。**

```
Proxmox Host
├── VM: OPNsense (2 vNIC: WAN bridge + LAN bridge)
├── VM: Test Client (1 vNIC: LAN bridge)
└── VM: SOCKS5 Proxy Server (1 vNIC: WAN bridge)
```

---

## 十、开始行动的第一步

**立即可做（今天就能开始）：**

1. **搭建测试环境** — 在虚拟机中安装 OPNsense
2. **交叉编译 tun2socks** — 在开发机上 `GOOS=freebsd GOARCH=amd64 go build`
3. **手动跑一遍 PoC** — SSH 到 OPNsense，手动执行 Step 0.3 的命令

如果 PoC 成功，就有了充足的信心继续 Phase 1 的开发。如果失败，在投入大量时间之前就能发现问题并调整方向。

---

*这份评估的核心结论：设计方向正确，架构合理，拓展性强。最大的不确定性在于 FreeBSD/OPNsense 上的底层兼容性，因此必须先做 PoC 验证再投入开发。*
