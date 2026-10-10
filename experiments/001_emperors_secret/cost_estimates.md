# Cost estimate — checked 2026-10-11

These are planning figures for a **later** approved run with exactly three five-second clips per provider at 720p, one take each. There were no paid calls during package preparation. Taxes, image creation, storage, retries, exchange fees, promotions, and account-specific discounts are excluded. Currency totals are kept separate rather than converted using a fluctuating exchange rate.

| Provider and region | Published rate used | One 5 s scene | Three scenes / 15 s |
| --- | --- | --- | --- |
| Vidu Q3 Turbo I2V, standard 720p | 12 credits/s × USD 0.005/credit | 60 credits ≈ USD 0.30 | 180 credits ≈ **USD 0.90** |
| Wan 2.7 I2V, Singapore 720P | CNY 0.733924/s | ≈ CNY 3.67 | ≈ **CNY 11.01** |
| Wan 2.7 I2V, Beijing alternative 720P | CNY 0.60/s | CNY 3.00 | **CNY 9.00** |

The [current Vidu pricing page](https://platform.vidu.com/pricing) lists **12 credits/s** for Q3 Turbo image/text/keyframe at 720p and USD 0.005 per credit. A separate [Vidu documentation pricing page](https://platform.vidu.com/docs/pricing) shows **11 credits/s** for the same nominal tier; the pages disagree. The table uses the current account-pricing page and is **not** an authorization to spend. Check the console quote immediately before any real task. Vidu's off-peak rate is not selected in this design.

Alibaba's [Model Studio pricing table](https://help.aliyun.com/en/model-studio/model-pricing) lists `wan2.7-i2v` at CNY 0.733924/s for Singapore and CNY 0.60/s for Beijing at 720P. The chosen template is Singapore. Model availability, region, quota, and any applicable free allowance require an account check. Wan may synthesize audio even when the prompt asks for none; the estimate uses the listed Wan 2.7 I2V rate, not a hypothetical silent discount.

If either provider fails, pauses, or bills at a different rate, stop the later experiment and revise this estimate before any retry. Offline checks have **zero provider cost**.
