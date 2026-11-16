# 安装到已有 Ren’Py 项目

## 首次安装

1. 下载 Release 的 `renpy-spine-v*-all.zip`。仅需 Windows 或 Android 时，也可选择对应平台包；`source.zip` 是开发源码，需要自行构建。
2. 解压后，把其中的 **spine 文件夹**复制到项目的 **game 文件夹**。安装后的入口应为 `你的项目/game/spine/spine_runtime.rpy`。
3. 完全退出旧游戏进程，再从 Ren’Py 启动器启动项目。在现有剧情标签中添加 `call renpy_spine_example` 可检查方块动画与指针交互。

不要用安装包替换整个 game 文件夹，也不要把仓库或源码 ZIP 整体放入 game。平台安装包和 all 合包的所有文件均位于 spine 内，包含 Python 模块、原生库、工具、示例、文档与许可。

插件不包含 script.rpy、screens.rpy、options.rpy 或 gui.rpy，不定义 start 标签。正常项目的剧情、界面和设置文件无需改动。Python 使用 Ren’Py 的 `renpy.add_python_directory` 注册 spine/python，不修改引擎或系统 Python 环境；原来的 `Spine(...)` 调用方式与 `renpy_spine` 模块名保持不变。

若项目已有同名 spine 文件夹，请核对里面是否为这个插件。与本插件同路径的文件、同名全局 API 或自定义打包规则仍可能冲突；单目录安装不代表消除所有代码层面的命名冲突。升级前保留自己修改过的插件文件。

## 从 v0.2.0 或之前的分散目录升级

完全关闭游戏后，先确认以下路径属于旧版 renpy-spine，并保留其中的自定义改动，再清理旧插件文件：

- `game/spine_runtime.rpy` 和 `game/spine_runtime.rpyc`：旧入口，必须清理，避免与新入口重复初始化。
- `game/python-packages/renpy_spine/`：旧 Python 包，必须清理，避免优先导入旧代码。保留 python-packages 内的其他库。
- `game/tools/spine/`：旧构建与打包工具，改用 `game/spine/tools/`。保留 tools 内其他工具。
- 如果以前手动复制过示例，清理 `game/spine_example.rpy` 和 `game/spine_example.rpyc`，避免同名标签重复。

**保留 `game/spine/assets/` 中自己的模型，不要删除整个 spine 文件夹。**将新包的 spine 内容合并进去，用新包提供的同名插件文件和原生库更新旧版。默认示例仅使用 `assets/adapter_sample`，自己的模型请使用其他子目录。重新启动游戏。

新入口检测到旧根目录入口或旧 Python 包时会提示清理，而不继续混用两份代码。模块名虽然保留，跨版本存档仍应在自己的项目中验证。

以后升级保持同样的单目录结构。需要卸载时，先移除剧情中对插件 API、示例及对象的引用，再移走 spine 文件夹；如内含自己的模型，应先另行保留。

## Android

all 合包包含 Windows 调试库及 Android 三种 ABI 的库，无需再合并两个下载包。Android 单独包不含 Windows 库。

先通过 Ren’Py/RAPT 生成 APK/AAB，再运行：

```powershell
python .\game\spine\tools\package-android.py 'C:\build\your-game.apk' --renpy-sdk 'C:\RenPySDK'
```

该工具需要对应 Android SDK/JDK 与签名密钥，每次重新构建后都需重新执行。签名、对齐和参数见 BUILDING.md；尚未完成 Android 真机验证。
