# Blind visual evaluation rubric

The coordinator first fixes three reviewed production start frames and records their SHA-256 hashes. Each model gets one take for each scene with the same frame and prompt; retain failures as failures rather than silently regenerating. Randomly assign the complete three-clip model sets to A and B and keep the reveal mapping outside Git. Strip or mute audio in the review player. Play each clip at normal speed twice, then once frame by frame if needed. Reviewers should not see provider names, filenames, metadata, or costs.

Score each criterion from **1 (major failure)** to **5 (excellent)**; use `NA` only if no playable clip exists and explain why. The sheet's `artifacts` field is scored high when artifacts are *absent*.

| Criterion | What to inspect |
| --- | --- |
| `first_frame_fidelity` | Opening composition, props, costume, and face match the locked starting frame. |
| `face_identity` | Lin Yue's oval face, brows, eyes, and left-eye beauty mark stay recognizable through motion. |
| `hair_costume` | Low braided bun, jade hairpin, teal cross-collar hanfu and sleeves remain stable. |
| `motion_adherence` | Intended action occurs at a natural pace without a cut or new person. |
| `camera_composition` | Close/medium vertical framing stays legible and follows the requested movement. |
| `artifact_absence` | Hands, decree, candle, door, fabric and background avoid warping, merging or flicker. |
| `cross_scene_identity` | **Set-level only:** Lin Yue looks like one person across all three clips. |

For each clip, average the six clip criteria with equal weight. For each set, average its three clip means and its `cross_scene_identity` score with equal 50% weight. Record any missing clip separately; a failed generation makes the set incomplete rather than awarding a quality score of zero. Prefer the set with the higher blinded aggregate. If the difference is under 0.5 on the five-point scale, report a tie and examine first-frame fidelity and cross-scene identity separately. Do not change the rubric after viewing outputs.

Record generation failures, elapsed time, output width/height, and charges outside the blind sheet. A coordinator may add a post-reveal operational comparison after all visual scores are locked. Three clips per model are a small exploratory sample, not a statistically reliable ranking.
