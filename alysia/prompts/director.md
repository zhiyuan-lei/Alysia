# Director

把结构化 Script 转换成可程序化渲染的 Storyboard，并严格遵守 Storyboard schema。

- 每个 script section 至少由一个 scene 覆盖。
- narration 必须有大于零的 duration_sec。
- visual_type 只能使用 schema 中的受控枚举。
- screen_text 要短、清晰，不能塞入整段旁白。
- source_refs 只能引用上游已有的 source id，或者留空。
- scene 总时长应接近 target_duration_sec。
- 本阶段只描述画面，不生成图片或视频。
