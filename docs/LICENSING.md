# 许可与公开分发范围

核对日期：2026-11-14。以下是项目的分发说明，不构成法律意见，也不保证不存在第三方权利争议。

## 官方条款

- [Spine Runtimes License Agreement](https://esotericsoftware.com/spine-runtimes-license)
- [Spine Editor License Agreement](https://esotericsoftware.com/spine-editor-license)，尤其第 2 节
- [固定的 3.8 源码及其原始许可证](https://github.com/EsotericSoftware/spine-runtimes/tree/8b4844bd4b193ba9e54487ed397a777993cbad56)

2026-11-14 获取的官网 Runtime 条款明确附带条件：产品用户须各自获得 Spine Editor 授权，除非集成方持有授权并满足 Editor 协议第 2 节；不得公开提供替代 Spine Editor 创建或编辑骨骼、动画的产品；任何形式的再分发都须保留许可和版权声明。该版本对 user 的定义排除了仅用于集成或评估 Runtime 的使用。完整、优先适用的表述见英文原文 [LICENSE](../LICENSE)。

Editor 协议第 2.4 节专门说明：使用 SDK、游戏工具包或库创建含 Runtime 的新应用时，该应用本身也是 Product，其开发者仍需取得自己的 Editor 授权。不要将“下载开源适配器”理解成获得 Spine Editor 或免除应用开发、修改和分发条件。

因此，在未确认持有 Editor 授权的情况下，本仓库作为源码适配器和集成/评估工具公开；它不提供免授权发行商业或免费游戏的承诺。用于正式开发、持续修改或交付游戏前，应先确认自己满足对应授权路径；有不确定之处请向 Esoteric Software 取得书面解释。

## 原始许可证与当前许可证

官方 Runtime 固定在 3.8 提交 `8b4844bd4b193ba9e54487ed397a777993cbad56`，其原始许可证日期为 2019-05-01，保存于 [LICENSES/Spine-Runtimes-3.8.txt](../LICENSES/Spine-Runtimes-3.8.txt)。下载工具也会逐字下载并校验该版本的 LICENSE。

官网当前许可证日期为 2026-11-14，声明替换之前版本，原文保存为根目录 [LICENSE](../LICENSE)。这里同时保留两份文本以反映源码来源及核对时的当前条款，不主张仅因固定旧提交就能规避后续条款；具体适用关系以权利方协议和解释为准。

原始适配代码、C 桥接、工具和几何示例按所附 Runtime 协议条件提供，版权归本项目贡献者；上游版权仍归 Esoteric Software。没有为集成部分附加 MIT / Apache 等宽松许可。

## 本仓库发布了什么

Git 仓库和源码 ZIP 公开适配源码、桥接、下载/构建/Android 打包工具、固定源码哈希清单、文档、自制几何示例和测试，不内置下载的官方 Runtime 源码。下载脚本从官方仓库获取并校验五个版本，不提供编辑器、激活工具或绕过授权的功能。

从 v0.2.0 起，Release 的 Windows 和 Android ZIP 另外包含五个后端的编译库。所有安装包保留当前 LICENSE、NOTICE、各锁定版本的原始许可和使用说明；新增原始许可保存于 LICENSES/Spine-Runtimes-4.x.txt 和 game/spine/SPINE-RUNTIME-4.x-LICENSE.txt。它们与源码、最终应用一样受适用的 Spine 条款约束，不提供免授权开发或分发的承诺。源码与二进制分离不会自动排除集成产品的许可义务。

没有上传本地测试使用的第三方角色立绘、骨骼文件、语音、音乐或截图。用户提供文件并不当然证明拥有公开再分发权，相关素材授权与 Runtime 授权是两件事。请仅使用有权使用和分发的自有素材。
