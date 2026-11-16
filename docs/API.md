# 动画、输入与事件

`spine_runtime.rpy` 向 Ren’Py store 注册 `Spine`、`SpineInteraction`、`TouchRegion` 和 `PointerBinding`。先安装 Release 或完成 README 中的源码构建。3.8、4.0、4.1、4.2、4.3 共用相同 API，按资源内部版本自动选择后端。

## Spine

```python
actor = Spine("spine/assets/model/model.skel", atlas=None,
    animation="idle", loop=True,
    size=(1280, 720), origin=(640, 640), zoom=0.5,
    skeleton_scale=1.0, default_mix=0.2, fps=60)
```

`atlas=None` 时使用骨骼文件同名 atlas；PNG 文件名来自 atlas，放在其同目录。通过 Ren’Py 文件 API 读取资源，支持 RPA。`size` 为画布尺寸，`origin` 为 Spine 原点在画布中的位置；骨骼坐标 Y 轴向上，画布坐标 Y 轴向下。

```python
actor.animations                         # {动画名: 秒数}
actor.bones                              # 骨骼名称
actor.stats                              # 最近绘制的批次与顶点统计
actor.play("idle", track=0, loop=True)
actor.queue("wave", track=0, loop=False, delay=0.0)
actor.play("face", track=1, alpha=0.5, additive=True)
actor.clear(track=1, mix=0.2)
actor.clear()                            # 清空全部轨道
actor.queue_empty(track=1, mix=0.2, delay=1.0)
actor.set_mix("idle", "wave", 0.25)
actor.set_skin("default")
actor.set_bone("control", x=20, y=10, rotation=8)
actor.reset_bone("control")
actor.get_bone("control")
actor.set_paused(True)
actor.set_speed(0.5)
actor.set_view(origin=(640, 600), zoom=0.6)
actor.canvas_to_bone("root", 640, 600)
actor.bone_to_canvas("root", 0, 0)
```

轨道为 0–31。非循环动画结束会保留最终姿势；临时表情等叠加轨道应排队空动画以释放覆盖。`queue_empty` 的 delay 是排队时间语义；希望先播完整个叠加动画，可以显式传入它的时长。

骨骼可覆盖 `x/y/rotation/scale_x/scale_y/shear_x/shear_y`。覆盖发生在应用动画后、世界变换与约束求解前。IK 等约束仍可能影响最终结果。

3.8 保留原来的紧凑存档快照；4.x 保存压缩操作记录，加载时重放以还原混合、附件序列和物理状态，过去事件不会重复触发。4.x 的记录内存和恢复时间随实例累计操作增长；不保证长时间播放后的读档耗时固定。临时鼠标/触摸覆盖在显示对象恢复时释放。请使用封装 API，直接修改 `native.lib` 不会进入 4.x 记录。

## 触摸和追踪

```renpy
default actor_input = SpineInteraction(actor,
    regions=(TouchRegion("head", "head_control", (90.0, 110.0),
        press=("touch",), release=("touch_end",), tracks=(3,)),),
    bindings=(PointerBinding("eye_control", "root",
        (600.0, 500.0), (30.0, 25.0)),),
    smoothing=0.09)

screen actor_screen():
    add actor_input
    on "hide" action Function(actor_input.cancel)
    textbutton "存档" action [Function(actor_input.cancel), ShowMenu("save")]
```

替换示例中的骨骼和动画名；不存在时会报错。触摸轨道应与剧情的待机、表情轨道分开。

| 声明 | 参数含义 |
| --- | --- |
| `TouchRegion(name, bone, radius, center=(0,0), press=(), release=(), tracks=(3,4))` | `bone` 局部空间中的椭圆；动画与轨道按顺序配对 |
| `PointerBinding(bone, reference, radius, limits, mode="hover", center=(0,0), regions=())` | 把相对 `reference` 的指针位置映射到控制 `bone` 的局部 x/y |

范围随骨骼完整仿射矩阵移动。重叠时优先匹配先声明的区域。`radius` 两个值必须为正；`limits` 控制最大 x/y 位移；控制骨骼应是以局部 x/y 零位为中心的专用骨骼。

`mode="drag"` 取按压起点后的相对位移，`regions=("head",)` 可限定能触发拖动的区域。`smoothing=0` 关闭平滑。

```python
actor_input.set_touch(False)
actor_input.set_follow(False)
actor_input.set_debug(True)
actor_input.cancel()
actor_input.input_events()    # 读取并清空 press/release/cancel 队列
```

输入事件含 `type`、`region`、`position`，位置为画布局部坐标。队列最多 128 条，与 Spine 动画事件独立。隐藏、更换模型或进入自定义菜单前调用 `cancel()`。追踪的逐帧覆盖保存在临时会话，不逐帧写入回滚控制器。存档会保留开关，读档会取消按住状态，并执行对应结束动作。

## 动画事件与声音

`actor.events()` 读取并清空 Spine 事件队列，最多暂存 256 条。`type=5` 是自定义事件，`type=3` 是动画完成；字段还包括 `track/name/time/integer/number/text/audio/volume/balance`。

渲染中只收集事件，不执行游戏逻辑。用 screen timer 或交互动作定期读取。以下例子只在自己有权使用的音频存在时生效：

```renpy
init python:
    renpy.music.register_channel("spine_voice", mixer="voice", loop=False)

    def dispatch_spine_voice(actor):
        from renpy_spine.audio import play_events
        play_events(actor, "spine/assets/model", channel="spine_voice")

screen voiced_actor():
    add actor
    timer 0.033 repeat True action Function(dispatch_spine_voice, actor)
```

不要直接把返回非空列表的 `play_events` 放入 `Function`：非空返回值可能结束 screen。游戏暂停/退出时，音频声道的同步由游戏逻辑处理。

## 存读档与版本

原生句柄和 GPU 对象不进入存档；保存的是版本化轨道快照与 Python 控制状态。常规控制状态参与 Ren’Py 回滚，旧鼠标坐标与按住状态不恢复。不同平台、插件版本或原生库版本之间迁移存档没有稳定兼容承诺。
