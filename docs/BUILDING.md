# 构建与打包

## 官方源码锁定

`game/tools/spine/runtime-lock.json` 记录官方 3.8 提交和逐文件 SHA-256；`runtime-lock-4.0.json` 至 `runtime-lock-4.3.json` 分别锁定新增后端。下载工具只获取清单内的文件并核对哈希，不动态选择“最新”提交。`--verify` 只检查已有文件。

本仓库与源码 ZIP 不内置 Runtime 源码。生成的 `vendor*`、官方示例、原生库和工具链均由 `.gitignore` 排除。GitHub Release 的平台安装包另外提供预编译库和所需许可。

`build-native.ps1` 会再次检查所有锁定哈希。编译前只在 `game/.spine-check/native-sources` 生成修正后的 `AnimationState.c`，不修改 vendor。修正把两处直接附件赋值替换为 `spSlot_setAttachment`，清除切换不同网格时遗留的变形。C 桥接还处理 270° 图集 UV，并对快照中的混合链和队列进行遍历约束。

4.0–4.2 通过 `bridge-4.c` 接入官方 C 运行时；4.3 使用 `bridge-4.3.cpp` 接入官方 C++ 运行时和 SkeletonRenderer。新增官方源码直接编译，不生成运行时补丁；构建前再次校验锁定清单。

构建脚本适用于 Windows 主机。Windows 使用 PATH 中的 MinGW-w64 x64 `gcc` / `g++`；Android 使用指定 NDK 的 Windows x64 `clang.exe`。4.3 静态链接 C++ 库；Windows 安装包无需额外复制 GCC DLL，Android 无需 `libc++_shared.so`。本地脚本不自动安装工具链，CI 的安装流程见 CI.md。

## Windows 游戏

按 README 构建后，正常使用 Ren’Py 启动器打包 Windows。`spine_runtime.rpy` 将 PNG / JSON / SKEL / atlas 放入资源归档，DLL 保持独立文件；排除构建工具和 Android 库。许可文件保留在 `game/spine`。完整发布物还应附带 NOTICE 和相关文档。

Windows 3.8 DLL 为 `renpy_spine_v1c.dll`，桥接 ABI 为 1；4.x 为 `renpy_spine_4_0.dll` 至 `renpy_spine_4_3.dll`，桥接 ABI 为 2。它们不链接 CPython / Ren’Py 头文件；但绘制使用内部 Python 接口，更新 Ren’Py 后仍须重新验证。运行时按资源版本选择 DLL，可以同时加载不同版本角色。

## Android 游戏

NDK r28 或更新版本，CI 固定 r28c，最低 API 21。三种 ABI 均配置 `max-page-size=16384` 和 `common-page-size=16384`。每个 ABI 包含原有 `librenpy_spine.so` 和四个 `librenpy_spine_4_x.so`；注入工具将它们全部加入原包已有的 ABI。插件 ELF 对齐不等于整个 APK 或引擎已经符合目标设备要求。

1. 在 Ren’Py / RAPT 安装对应 SDK / JDK，先正常构建游戏 APK 或 AAB。
2. 运行 `game/tools/spine/package-android.py`。原包保留，输出名默认为 `-spine` 后缀。

```powershell
python .\game\tools\spine\package-android.py 'C:\build\game.apk' --sdk 'C:\Android\Sdk' --keystore 'C:\keys\release.keystore' --alias release
```

默认密钥路径为游戏项目根目录的 `android.keystore`（APK）或 `bundle.keystore`（AAB），alias 和密码默认为 RAPT 的 `android`。自定义密码通过 `SPINE_STORE_PASSWORD` 和 `SPINE_KEY_PASSWORD` 环境变量传入；不要提交密钥或密码。

APK 注入后调用 SDK 的 zipalign 进行 16 KB 对齐，再由 apksigner 签名、验证。AAB 调用 jarsigner 签名、验证。`--unsigned` 生成供外部签名的产物；APK 对齐仍需 SDK build-tools，签名时必须最终验证。

工具只向原包已有的 ABI 添加插件库，避免添加缺少 Ren’Py 引擎库的新 ABI；不修改 RAPT 模板或原始包。每次重新从 Ren’Py 构建 Android 包后，都要重新注入。发布生成的新文件。

没有进行 Android 真机测试。正式交付前应检查安装启动、GPU 绘制、触屏、切后台、音频、存读档与回滚。

## 插件安装包

全部构建通过后，运行 `python tools/package-release.py` 在 `dist` 生成三个 ZIP、SHA256SUMS.txt、release-manifest.json 和发布说明。打包不会收集游戏目录中的任意文件，只按代码内明确列出的路径收集适配器、自制示例、文档、许可和指定原生库。与 VERSION 一致的标签会触发自动 Release，见 CI.md。
