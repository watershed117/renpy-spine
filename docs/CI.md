# CI/CD 与 Release

`.github/workflows/ci.yml` 在 `main` 推送、pull request、手动运行及 `v*` 标签推送时执行。无需保存个人 GitHub token；发布作业使用 GitHub 提供的 `GITHUB_TOKEN`，仅该作业申请 `contents: write`。

## 执行流程

1. Windows 作业安装 MinGW-w64，下载并校验五个固定版本源码，编译五个 DLL。使用自制 3.8 数据及 58 个官方 JSON/SKEL 检查播放、事件、队列、多轨、骨骼覆盖和存档恢复，再检查 PE 架构及动态依赖。
2. Android 作业固定使用 NDK r28c `28.2.13676358`，分别编译 arm64-v8a、armeabi-v7a、x86_64 的五个后端。检查全部 15 个 ELF 的 CPU 架构、16 KB 加载对齐与依赖，并用四种模拟 APK/AAB 布局检查注入逻辑。
3. 两个作业成功后，打包作业生成源码、Windows x64、Android 与 all 合包 ZIP，以及 SHA-256 和文件清单。安装包仅包含 spine 文件夹；安装检查将其解压到模拟已有项目，核对原项目文件未被改动。打包使用明确的文件白名单；不包含本地游戏资源、官方示例、下载的 vendor、工具链、密钥或缓存。固定输入的 ZIP 使用固定时间戳和文件顺序。
4. 仅标签推送会进入 Release 作业。标签必须等于 `v` 加 `VERSION`。作业先创建草稿，上传并校验六个附件后公开；发生错误时保持草稿。不会覆盖内容不同的已发布附件，应使用新版本。

每次正常构建可在 Actions 的 artifacts 下载 `release-assets`；Windows/Android 原生库和检查报告也分别保留。该流程发布的是插件安装包，不是已签名游戏 APK，也不使用你的 Android 签名密钥。

## 发布新版本

更新 `VERSION` 和 `CHANGELOG.md` 中对应的 `## x.y.z` 段落，再提交：

```powershell
git add .
git commit -m "Prepare v0.3.0"
git push origin main
git tag -a v0.3.0 -m "Release v0.3.0"
git push origin v0.3.0
```

示例中的版本必须与实际 `VERSION` 一致。全部构建、测试和打包通过后，Release 才会公开。失败时先查看 Actions 日志并修复，再发布新版本；不要移动已公开版本的标签。

## 本地复现

```powershell
node game/spine/tools/fetch-runtime.cjs
node game/spine/tools/fetch-multiversion.cjs
node game/spine/tools/fetch-multiversion.cjs --fixtures
./game/spine/tools/build-native.ps1 -Target windows
./game/spine/tools/build-multiversion.ps1 -Target windows
./game/spine/tools/build-native.ps1 -Target android -Ndk 'C:/Android/android-ndk-r28c'
./game/spine/tools/build-multiversion.ps1 -Target android -Ndk 'C:/Android/android-ndk-r28c'
python tests/native-smoke.py
python tests/native-multiversion.py
python tests/audit-native.py
python tests/android-package.py
python tools/package-release.py
```

Action 使用完整提交哈希固定版本；官方源码和示例使用提交加逐文件 SHA-256。更新它们时应同时审核清单变化和运行回归。编译器包与 GitHub runner 镜像会更新，因此不承诺不同时间生成的原生二进制逐字节一致。

CI 没有安装 Ren’Py GPU 窗口或 Android 设备，不能代替真实游戏的渲染、输入、存读档和设备验收。Ren’Py 接入层的本地验证范围见 VALIDATION.md。
