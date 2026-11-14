# renpy-spine

在 Ren’Py 中实时播放 **Spine 3.8** 骨骼动画，并支持骨骼触摸区域、拖动和鼠标追踪。无需修改 Ren’Py 引擎源码。

A source adapter for Spine 3.8 and Ren’Py, with native animation, bone-space touch regions and pointer tracking. **Spine licensing applies.**

这是源码与构建工具包：不附带官方运行时源码、DLL / SO、Spine Editor、第三方角色、语音或音乐。示例仅使用本项目自制的方块与指针标记。构建后才能运行。

## 使用许可

公开仓库不代表可以免授权使用 Spine。请先阅读 [许可说明](docs/LICENSING.md)、[LICENSE](LICENSE) 与 [NOTICE](NOTICE)。适配器按所附 Spine Runtimes License 的条件提供，不采用 MIT 等无限制的宽松授权。

未确认持有 Spine Editor 授权时，应把当前用途限制在条款允许的集成与评估范围；使用本工具开发或修改含 Spine Runtime 的应用，以及分发给最终用户，须另行满足官方条款。只发布适配源码并不能消除所有许可义务。

## 支持范围

| 项目 | 范围 |
| --- | --- |
| Ren’Py | 验证版本为 8.5.3.26051504，使用 GL2 的内部 Mesh2 / AttributeLayout 接口 |
| Spine 导出 | 3.8 JSON / SKEL + atlas + PNG；不支持 4.x，显式拒绝 3.8.75 |
| Windows | x64；使用 MinGW-w64 GCC 从源码编译 |
| Android | 构建支持 arm64-v8a / armeabi-v7a / x86_64，API 21，16 KB ELF 对齐 |
| Android 验证 | 已完成原生库结构和注入逻辑检查；尚未完成 APK 安装与真机触摸验证 |
| 其他平台 | macOS / Linux / iOS / Web 尚未适配 |

支持实时骨骼、IK、网格与变形、裁剪、图集旋转、双色着色、混合模式、多轨、动画队列、混合、皮肤、骨骼覆盖、事件、暂停、速度、存读档和回滚。触屏共用 Ren’Py 的主触点鼠标事件，不提供多指手势。

## 安装与构建

以下命令在 Windows PowerShell 中运行。安装 Node.js 18+、MinGW-w64 x64 GCC、Python 3 和 Ren’Py SDK。GCC 必须能从 PATH 找到。

1. 在满足许可条件的前提下，下载并校验固定版本的官方 C 运行时：

   ```powershell
   node .\game\tools\spine\fetch-runtime.cjs
   node .\game\tools\spine\fetch-runtime.cjs --verify
   ```

   若本机通过 Windows 系统证书信任网络代理，可在支持该选项的新版 Node.js 上使用 `node --use-system-ca ...`；请保留 TLS 证书校验。

2. 编译 Windows 动态库：

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\game\tools\spine\build-native.ps1 -Target windows
   ```

3. 把本仓库 `game` 目录的内容合并到你的 Ren’Py 项目 `game` 中，包括生成的 `spine/native` 与两份 `spine/*LICENSE.txt`。同时在游戏文档中保留根目录 [NOTICE](NOTICE) 和许可说明。不要把仓库根目录作为普通子目录放进现有 `game`，Ren’Py 会递归加载 `.rpy`。

4. 可选：把 `examples/game` 的内容也合并到游戏的 `game` 目录，在剧情里调用：

   ```renpy
   call renpy_spine_example
   ```

   示例窗口显示旋转方块：按住方块触发动画，指针标记平滑跟随鼠标。也可切换触摸范围显示与追踪。示例使用自己的 screen，不覆盖你的 `start` 标签。

Windows 构建产物为 `game/spine/native/windows-x86_64/renpy_spine_v1c.dll`。升级 Python 插件时，请同时重新编译原生库并完全退出旧游戏进程。

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
python .\game\tools\spine\package-android.py 'C:\build\your-game.apk' --renpy-sdk 'C:\RenPySDK'
```

先通过 Ren’Py / RAPT 正常生成 APK / AAB，再执行注入工具。发布生成的 `*-spine.apk` / `*-spine.aab`。签名与验证参数见 [构建说明](docs/BUILDING.md)。

## 验证与维护

```powershell
python .\tests\native-smoke.py
```

使用仓库自制的几何数据检查绘制、动画事件、队列、多轨存档恢复与骨骼矩阵；不需要任何第三方素材。请先构建 Windows 库。

初次整理前，实际项目已通过存读档、回滚、触摸结束、仿射坐标往返、追踪限位、输入取消等逻辑回归。仓库自身的验证记录见 [验证范围](docs/VALIDATION.md)。它们不能代替你自己的素材、目标 GPU 和设备测试。

Ren’Py 内部绘制 API 可能随版本改变；更新 SDK 后应重新检查绘制、存读档、回滚和输入。固定的 3.8 Runtime 不会自动升级到新主版本。
