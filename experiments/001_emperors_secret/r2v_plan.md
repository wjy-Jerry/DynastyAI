# Later R2V character-consistency test — design only

This is a separate follow-up after the I2V visual scorecard is closed. No R2V API adapter, request, or task is implemented by Experiment 001.

1. Freeze and hash one reviewed `assets/lin_yue_reference.png`: a single unobstructed Lin Yue portrait with her fixed face, braid, jade hairpin, and teal hanfu. Keep the three reviewed scene frames and their hashes unchanged.
2. For Wan 2.7 R2V, test the documented combination of each scene's `first_frame` **plus** the same `reference_image` portrait. Use the same 5-second scene action, 720P, and no prompt rewriting. Wan's documentation explicitly supports this combination. [Wan R2V API](https://help.aliyun.com/en/model-studio/wan-video-to-video-api-reference)
3. Check Vidu Q3 Turbo R2V's current input contract before designing its matched arm. Do not assume that its reference-to-video endpoint accepts a fixed first frame. If it cannot lock both the reference portrait and each scene's first frame, compare Vidu R2V against its own I2V baseline only, and label the cross-provider comparison as non-equivalent. [Vidu R2V documentation](https://platform.vidu.com/docs/reference-to-video)
4. Keep the same number of takes, scenes, prompt intent, resolution tier, and blind A/B scoring. Add a third-party reviewer score for face identity across scenes, plus hairpin and costume continuity. Record pose and lighting differences so they are not mistaken for identity drift.
5. Score the *change* from each provider's I2V baseline to its R2V result, rather than claiming perfect identity consistency. If R2V changes camera framing, scene content, or output audio, report those differences separately. Recheck prices and request explicit authorization before any live call.

The portrait specification is a control target, not a generated asset in this package.
