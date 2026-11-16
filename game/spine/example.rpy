# Original geometric example; see LICENSE and NOTICE at repository root.
# Only creates the sample actor when the example label is called.

screen renpy_spine_example_screen(spine_example_input):
    modal True
    add Solid("#152436")
    add spine_example_input xalign 0.5 yalign 0.5
    vbox:
        xalign 0.5
        yalign 0.03
        spacing 8
        text "renpy-spine / geometric sample" xalign 0.5
        text "Hold the box; move the pointer." xalign 0.5
    hbox:
        xalign 0.5
        yalign 0.96
        spacing 28
        textbutton "Touch" action Function(spine_example_input.set_touch, not spine_example_input.settings.touch)
        textbutton "Follow" action Function(spine_example_input.set_follow, not spine_example_input.settings.follow)
        textbutton "Regions" action Function(spine_example_input.set_debug, not spine_example_input.settings.debug)
        textbutton "Back" action [Function(spine_example_input.cancel), Return()]
    key "game_menu" action [Function(spine_example_input.cancel), Return()]
    on "hide" action Function(spine_example_input.cancel)

label renpy_spine_example:
    call screen renpy_spine_example_screen(SpineInteraction(
        Spine("spine/assets/adapter_sample/sample.json",
            animation="idle", size=(960, 540), origin=(480, 270), zoom=2.0),
        regions=(TouchRegion("box", "body", (45.0, 45.0),
            press=("touch",), release=("touch_end",), tracks=(3,)),),
        bindings=(PointerBinding("pointer", "root", (240.0, 135.0), (100.0, 55.0)),)))
    return
