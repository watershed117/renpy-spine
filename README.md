# renpy-spine

在 Ren’Py 中实时播放 **Spine 3.8、4.0、4.1、4.2、4.3** 骨骼动画，自动选择匹配的官方运行时，支持骨骼触摸区域、拖动和鼠标追踪。无需修改 Ren’Py 引擎源码。

An adapter for Spine 3.8–4.3 and Ren’Py, with native animation, bone-space touch regions and pointer tracking. **Spine licensing applies.**

Git 仓库与源码 ZIP 不内置官方运行时源码或编译产物。Release 提供含全部五个后端的 **Windows x64** 和 **Android 三种 ABI** 安装包，可直接使用；也可从锁定源码自行构建。示例仅使用本项目自制的方块与指针标记，不分发第三方角色、语音、音乐或 Spine Editor。

## 下载 Release

在仓库的 Releases 页面选择 `v0.2.0` 或后续版本：

- `renpy-spine-v*-windows-x86_64.zip`：Python/Ren’Py 接入代码、五个 DLL、自制示例及许可。
- `renpy-spine-v*-android.zip`：接入代码、三种 ABI 各五个 SO、APK/AAB 注入工具及许可。
- `renpy-spine-v*-source.zip`：完整适配源码、固定源码清单、构建工具与 CI；需要自行下载官方源码并编译。
- `SHA256SUMS.txt` 和 `release-manifest.json`：校验附件及查看完整文件列表。

安装时把对应 ZIP 中的 `game` 内容合并到自己的 Ren’Py 项目 `game`，并保留许可和 NOTICE。Android 包仍需先由 Ren’Py/RAPT 构建，再用注入工具加入原生库。详见 [构建说明](docs/BUILDING.md)。

## 使用许可

公开仓库不代表可以免授权使用 Spine。请先阅读 [许可说明](docs/LICENSING.md)、[LICENSE](LICENSE) 与 [NOTICE](NOTICE)。适配器按所附 Spine Runtimes License 的条件提供，不采用 MIT 等无限制的宽松授权。

未确认持有 Spine Editor 授权时，应把当前用途限制在条款允许的集成与评估范围；使用本工具开发或修改含 Spine Runtime 的应用，以及分发给最终用户，须另行满足官方条款。只发布适配源码并不能消除所有许可义务。

## 支持范围

| 项目 | 范围 |
| --- | --- |
| Ren’Py | 验证版本为 8.5.3.26051504，使用 GL2 的内部 Mesh2 / AttributeLayout 接口 |
| Spine 导出 | 3.8、4.0、4.1、4.2、4.3 的 JSON / SKEL + atlas + PNG；显式拒绝 3.8.75 |
| Windows | x64；使用 MinGW-w64 GCC 从源码编译 |
| Android | 构建支持 arm64-v8a / armeabi-v7a / x86_64，API 21，16 KB ELF 对齐 |
| Android 验证 | 已完成原生库结构和注入逻辑检查；尚未完成 APK 安装与真机触摸验证 |
| 其他平台 | macOS / Linux / iOS / Web 尚未适配 |

支持实时骨骼、IK、网格与变形、裁剪、图集旋转、双色着色、混合模式、多轨、动画队列、混合、皮肤、骨骼覆盖、事件、暂停、速度、存读档和回滚。触屏共用 Ren’Py 的主触点鼠标事件，不提供多指手势。

## 安装与构建

使用预编译 Release 可跳过编译。自行构建时，在 Windows PowerShell 中安装 Node.js 18+、MinGW-w64 x64 GCC/G++、Python 3 和 Ren’Py SDK；GCC/G++ 必须能从 PATH 找到。

1. 在满足许可条件的前提下，下载并校验固定版本的官方 C 运行时：

   ```powershell
   node .\game\tools\spine\fetch-runtime.cjs
   node .\game\tools\spine\fetch-runtime.cjs --verify
   node .\game\tools\spine\fetch-multiversion.cjs
   node .\game\tools\spine\fetch-multiversion.cjs --verify
   ```

   若本机通过 Windows 系统证书信任网络代理，可在支持该选项的新版 Node.js 上使用 `node --use-system-ca ...`；请保留 TLS 证书校验。

2. 编译 Windows 动态库：

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\game\tools\spine\build-native.ps1 -Target windows
   powershell -ExecutionPolicy Bypass -File .\game\tools\spine\build-multiversion.ps1 -Target windows
   ```

3. 把本仓库 `game` 目录的内容合并到你的 Ren’Py 项目 `game` 中，包括生成的 `spine/native` 与全部 `spine/*LICENSE.txt`。同时在游戏文档中保留根目录 [NOTICE](NOTICE) 和许可说明。不要把仓库根目录作为普通子目录放进现有 `game`，Ren’Py 会递归加载 `.rpy`。

4. 可选：把 `examples/game` 的内容也合并到游戏的 `game` 目录，在剧情里调用：

   ```renpy
   call renpy_spine_example
   ```

   示例窗口显示旋转方块：按住方块触发动画，指针标记平滑跟随鼠标。也可切换触摸范围显示与追踪。示例使用自己的 screen，不覆盖你的 `start` 标签。

Windows 构建产物包括 `renpy_spine_v1c.dll` 及 `renpy_spine_4_0.dll` 至 `renpy_spine_4_3.dll`，放在 `game/spine/native/windows-x86_64`。升级插件和原生库后，请完全退出旧游戏进程。

## 基本用法

```renpy
default actor = Spine(
    "spine/assets/your_model/model.skel",
    animation="idle",
    size=(1280, 720), origin=(640, 640), zoom=0.5,
)

label show_actor:
    show expression actor as live_actor
    $ actor.play("wave", loop=False)
    $ actor.queue("idle", loop=True)
    "动画在剧情交互中持续播放。"
    hide live_actor
    return
```

`Spine` 可以直接 `show expression` 或在 screen 中 `add`。动画名、骨骼名和控制区域均来自自己的素材。完整说明见 [API 与交互](docs/API.md)。

## Android

```powershell
powershell -ExecutionPolicy Bypass -File .\game\tools\spine\build-native.ps1 -Target android -Ndk 'C:\Android\android-ndk-r28c'
powershell -ExecutionPolicy Bypass -File .\game\tools\spine\build-multiversion.ps1 -Target android -Ndk 'C:\Android\android-ndk-r28c'
python .\game\tools\spine\package-android.py 'C:\build\your-game.apk' --renpy-sdk 'C:\RenPySDK'
```

先通过 Ren’Py / RAPT 正常生成 APK / AAB，再执行注入工具。发布生成的 `*-spine.apk` / `*-spine.aab`。签名与验证参数见 [构建说明](docs/BUILDING.md)。

## 验证与维护

```powershell
python .\tests\native-smoke.py
node .\game\tools\spine\fetch-multiversion.cjs --fixtures
python .\tests\native-multiversion.py
python .\tests\audit-native.py
python .\tests\android-package.py
```

首个测试仅使用仓库自制几何数据。多版本测试按固定清单下载官方示例，覆盖 58 个 JSON/二进制文件，包括序列贴图和物理约束；下载的源码与官方示例不提交、不进入 Release ZIP。请先构建对应原生库。

4.x 使用压缩操作记录恢复官方运行时内部状态，内存和读档耗时随当前实例累计操作增长；3.8 保留原有紧凑快照。新增 4.x 官方源码未修改，现有 3.8 构建仍保留附件/眨眼修正。绘制层保留按内容跳过重复 Mesh2 上传的优化。

CI 会在 push / pull request 时构建、测试并生成附件；推送与 `VERSION` 一致的 `v*` 标签后自动发布 Release。流程与维护方式见 [CI/CD](docs/CI.md)。

初次整理前，实际项目已通过存读档、回滚、触摸结束、仿射坐标往返、追踪限位、输入取消等逻辑回归。仓库自身的验证记录见 [验证范围](docs/VALIDATION.md)。它们不能代替你自己的素材、目标 GPU 和设备测试。

Ren’Py 内部绘制 API 可能随版本改变；更新 SDK 后应重新检查绘制、存读档、回滚和输入。各后端固定到已校验的官方提交，不自动追踪上游分支。
