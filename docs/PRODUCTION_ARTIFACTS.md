# Production Artifacts

Production checkpoints and generated media artifacts live outside the source
tree. Keep main small and reproducible: source, registry metadata, test
receipts, and docs are committed; heavyweight model binaries and dashboards are
external artifacts with hashes.

## External root

Default local root:

```bash
/Volumes/OWC_8TB/gpr_work
```

Use the helper before training, gates, or artifact-heavy smoke tests:

```bash
source tools/dev/external_drive_env.sh
```

Important paths:

| variable | default | purpose |
|---|---|---|
| `GPR_MODEL_ROOT` | `/Volumes/OWC_8TB/gpr_work/models` | production checkpoints referenced by `pipelines/registry.json` |
| `GPR_CHECKPOINT_ROOT` | `/Volumes/OWC_8TB/gpr_work/checkpoints` | training checkpoints and candidates |
| `GPR_ARTIFACT_ROOT` | `/Volumes/OWC_8TB/gpr_work/artifacts` | dashboards, videos, generated reports |
| `TMPDIR` | `/Volumes/OWC_8TB/gpr_work/tmp` | Python/tool temporary files |
| `GATE_TMPDIR` | `/Volumes/OWC_8TB/gpr_work/gate_tmp` | quality-gate scratch |

## Required Registry Artifacts

Release mode verifies every checkpoint and registered training-pair field
referenced by `pipelines/registry.json`, not just the three core shipping model
files. This keeps experimental, diagnostic, and guardrail registry entries
reproducible while they remain registered. The current strict artifact inventory
is:

| CNN id | field | registry path | sha256 |
|---|---|---|---|
| `bibo1x_ane_gpr_tools_q3` | `ckpt_path` | `models/BayInBayOut_1x_AAon_w16_ANE_gpr_tools_q3.pt` | `df22af432710bddabd223047c2db2d0edf2808dd17c4341694a974e045ec87cd` |
| `bibo1x_ane_ml2_q3` | `ckpt_path` | `models/BayInBayOut_1x_AAon_w16_ANE_ML2_q3.pt` | `7fac7c28f13830c716fede8c9caf129fc7d949151508b70530449f13151fade9` |
| `bibo2x_ane_ml2_q3_dec2_diverse` | `ckpt_path` | `models/BayInBayOut_2x_AAon_w16_ANE_ML2_q3_dec2_diverse.pt` | `bd3636d2c026639e3d8c9636de491c662fe05e67bdaa4451061901b47b37659b` |
| `bido4x_ane_ml2_q3_dec2_lpips_detail_lumagrad_w001` | `ckpt_path` | `/Volumes/OWC_8TB/gpr_work/checkpoints/bido_target_detail_20260605/bido_4x_lpips005_detail_lumagrad_w001.pt` | `e538ad8d3d2f464beeb311484a84caebc1e4ec6c754bd94027b5a5933f861132` |
| `bido4x_w32_ml2_q3_dec2_hardtail_t192_lpips005_lumagrad0005` | `ckpt_path` | `/Volumes/OWC_8TB/gpr_work/checkpoints/bido_full_context_20260605/bido_4x_w32_hardtail_t192_lpips005_lumagrad0005_z6693holdout.pt` | `8fa6d260a0e2bb8b03e98fa8b09496811e1d297cbb3443d621f514ec8060cc6f` |
| `codec_raw_signal_sr_ml2_q3_dec2_w64_iso_expanded` | `ckpt_path` | `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_train_expanded_20260605/codec_raw_signal_sr_w64_iso_expanded_84crops.pt` | `376f1fa52989c62076684ffa39fedbf7a469b8bf7ab3e934a9260100d5dc328c` |
| `codec_raw_signal_sr_ml2_q3_dec2_w64_iso_expanded_runtime_sigma_probe` | `ckpt_path` | `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_train_expanded_20260605/codec_raw_signal_sr_w64_iso_expanded_84crops.pt` | `376f1fa52989c62076684ffa39fedbf7a469b8bf7ab3e934a9260100d5dc328c` |
| `codec_raw_signal_sr_ml2_q3_dec2_w64_iso_runtime_sigma_84crops` | `ckpt_path` | `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_train_runtime_sigma_20260605/codec_raw_signal_sr_w64_iso_runtime_sigma_84crops.pt` | `fb6e37a1e15ed297d47878b6144bebcbf5ed0ee675bfe5a141da401e5c497aeb` |
| `codec_raw_signal_sr_ml2_q3_dec2_w64_iso_only_84crops` | `ckpt_path` | `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_train_iso_only_20260605/codec_raw_signal_sr_w64_iso_only_84crops.pt` | `7de6e691813e39ae2d9d3ce1a0ed1682a90b2d702c0cb3ac6af2d01f1e9445cf` |
| `lab_chroma_corrector_w12_sips_residual_ab8_sub10` | `ckpt_y` | `/Volumes/OWC_8TB/gpr_work/cnn/F_ane_no_sr_w16_y_multival_hf05_grad02_sub4.pt` | `e7f5add8b7a3b4ed04f87417f7026b3d5a01ccfc0ee3eb403e4f8ced3eab661e` |
| `lab_chroma_corrector_w12_sips_residual_ab8_sub10` | `ckpt_chroma` | `/Volumes/OWC_8TB/gpr_work/cnn/F_ane_chroma_corrector_w12_sips_residual_ab8_sub10.pt` | `cbb6bde6f0bdb36eb50f202f2031fec2447fea12379125211475b0e886ff4677` |
| `mission1_native12_8k_sr_all24_holdout5_v1` | `ckpt_path` | `artifacts/mission1_z8_sr_all24_current_t233_20260618/mission1_z8_all24_sr_current_t233_lowps_w48_d6_rs03_holdout5_12k.pt` | `e077e8bf1ad24d959867ea22786a37f1e5587fd5a4c28565bb0dbeb7739d03ca` |
| `mission1_native12_8k_sr_all24_holdout5_v1` | `training_pairs_path` | `artifacts/mission1_z8_sr_all24_current_t233_20260618/mission1_z8_all24_sr_pairs_current_t233_gaussian_area_96t_w96.npz` | `1bfdb14606cf42490ce2c769795808c4fea74c5846a445ef19d68e5354d30221` |
| `mission1_native12_8k_sr_focus_hardrows_2500_v1` | `training_pairs_path` | `artifacts/mission1_z8_sr_all24_current_t233_20260618/mission1_z8_all24_sr_pairs_current_t233_gaussian_area_96t_w96.npz` | `1bfdb14606cf42490ce2c769795808c4fea74c5846a445ef19d68e5354d30221` |
| `mission1_native12_8k_sr_guardrail_focus_1500_v1` | `ckpt_path` | `artifacts/mission1_sr_t233_guardrail_focus_20260618/mission1_sr_t233_guardrail_focus_from_focus_w48_d6_rs03_1500.pt` | `9a8ce5c936da1ae26823b1ce613aabb510e7c124004fa2b5b786a69ba74d7508` |
| `mission1_native12_8k_sr_guardrail_focus_1500_v1` | `training_pairs_path` | `artifacts/mission1_z8_sr_all24_current_t233_20260618/mission1_z8_all24_sr_pairs_current_t233_gaussian_area_96t_w96.npz` | `1bfdb14606cf42490ce2c769795808c4fea74c5846a445ef19d68e5354d30221` |
| `mission1_native12_8k_sr_guardrail_light_w15_800_v1` | `training_pairs_path` | `artifacts/mission1_z8_sr_all24_current_t233_20260618/mission1_z8_all24_sr_pairs_current_t233_gaussian_area_96t_w96.npz` | `1bfdb14606cf42490ce2c769795808c4fea74c5846a445ef19d68e5354d30221` |

The Mission 1 native-12 8K SR candidate also records external training and
holdout evidence in `pipelines/registry.json`:

| artifact | path | sha256 |
|---|---|---|
| merged Mission1+Z8 SR pairs | `artifacts/mission1_z8_sr_all24_current_t233_20260618/mission1_z8_all24_sr_pairs_current_t233_gaussian_area_96t_w96.npz` | `1bfdb14606cf42490ce2c769795808c4fea74c5846a445ef19d68e5354d30221` |
| five-Z8 full-frame holdout summary | `artifacts/mission1_z8_sr_all24_holdout5_fullframe_20260618/summary.json` | `1fee957ade13e93e2f77f958932ecd35b336363bd103a4626bb0a660cf317f81` |
| Mission1 GP017604 full-frame holdout summary | `artifacts/mission1_sr_all24_holdout5_GP017604_fullframe_20260618/summary.json` | `c8d3e72975b1e1b0bf6358c50394d32242fbab31a11af346ac9d5acd0295e87a` |
| Mission1 eight-frame broad full-frame holdout summary | `artifacts/mission1_sr_all24_holdout8_fullframe_20260618/summary.json` | `a3a163f35fdf69554b0957da7c59f056b3744240d5e1ad4c09cc40f01ad520c5` |
| `.gvid` decode-to-SR smoke receipt | `artifacts/mission1_native12_gvid_to_8k_sr_smoke_20260618/receipt.json` | `ca6657aa17e9be96eecc3d413a9ef9a322561c36e803343e8ce5849ed3cf7230` |
| registry-driven `.gvid` decode-to-SR smoke receipt | `artifacts/mission1_native12_gvid_to_8k_sr_registry_smoke_20260618/receipt.json` | `d4c49fcacd838d6cbee2e425bab4ddaccf1b1dd2049b5763f28f590042819d13` |
| `.gvid` multi-frame decode-to-SR receipt | `artifacts/mission1_native12_gvid_to_8k_sr_multiframe_20260618/receipt.json` | `8b438a2d112527aadba0029c0c81eee4a2bc038f7b3be87af9308986be6d8d77` |
| `.gvid` SR packaging receipt | `artifacts/mission1_native12_gvid_to_8k_sr_packaging_20260618/packaging_receipt.json` | `22ef04b34fe0a6c402164c86616f6ca528645ce392b82c3ea6b65ab8a70662e6` |
| Mission 1 numbered-list readiness audit | `artifacts/mission1_numbered_list_readiness_20260625/readiness.json` | `94c9af897ba498bd3547f8f9b267dee8a8c42865ee150d65e064ce14426bafab` |
| Mission 1 numbered-list readiness audit Markdown | `artifacts/mission1_numbered_list_readiness_20260625/readiness.md` | `2b3a62758f463d6a414f702267f4e584c33f4a1e26f4ca191f6efdf7fe4842f4` |
| Mission 1 numbered-list closure plan | `artifacts/mission1_numbered_list_readiness_20260625/closure_plan.json` | `7994fcd014632d6b7e9d46e51990a38cae5c59cbe20c348d356e62cea02224a1` |
| Mission 1 numbered-list closure plan Markdown | `artifacts/mission1_numbered_list_readiness_20260625/closure_plan.md` | `763a23bfbe6cb5e7508f36d4153f0dcd344de4b05bed127d2df45bc28a783058` |
| Mission 1 camera target preflight | `artifacts/mission1_camera_target_preflight_20260625/preflight_192_168_16_67.json` | `29792898a2f59b9198823eb1d1e35d1378734ac413abd5dfc06ea0a322a3c53b` |
| Mission 1 current Pi target preflight with Labs shim | `artifacts/mission1_camera_target_preflight_20260625/preflight_192_168_16_67_standin_current_20260625.json` | `ad48eb6da9a14f7e263dc4c8240638aef857c2f927825fa2bdc11ca5a475be74` |
| Mission 1 camera source endpoint probe | `artifacts/mission1_camera_target_preflight_20260625/source_probe_192_168_16_67_camera_sensor_ring_20260625.json` | `47ae3c9c6625211be633d8c711000b2018e48fda279c5120577e9eacbefd54ae` |
| Mission 1 follow-up camera source endpoint probe | `artifacts/mission1_camera_target_preflight_20260625/source_probe_192_168_16_67_camera_sensor_ring_followup_20260625.json` | `1400868bc33fe4da52da3aa17ca588a3775845fcb6ddfd43c19bad111859614d` |
| Mission 1 camera target source/display/storage discovery probe | `artifacts/mission1_camera_target_preflight_20260625/source_probe_192_168_16_67_discovery_20260625.json` | `cd28624fc5865e546df4ebdde87f617b47c3f87d0e284381fe836f41f07ff8fd` |
| Mission 1 target V4L/media capability snapshot | `artifacts/mission1_camera_target_discovery_20260625/v4l_media_capabilities_192_168_16_67_20260625.txt` | `ce0ecd78c41889c1f89622ce2e714c3a8440cf3c85173a939067d589bd1b5cff` |
| Mission 1 target rpicam/libcamera capability snapshot | `artifacts/mission1_camera_target_discovery_20260625/rpicam_capabilities_192_168_16_67_20260625.txt` | `89a908c79b85ccb406883253763e2878464d07df153d9e53458b11b416a14cbc` |
| Mission 1 target structured camera hardware audit | `artifacts/mission1_camera_target_discovery_20260625/hardware_audit_192_168_16_67_20260625.json` | `0be23aaf6fdc21a331bb29e122a5b51f1013d3e553608c64d2a3b45522fef57d` |
| Mission 1 live follow-up camera hardware audit | `artifacts/mission1_camera_target_discovery_20260625/hardware_audit_192_168_16_67_live_followup_20260625T233902Z.json` | `ccdf22402275d9f32ce39aa64a7ab561c2f872824d54242748dfb9edb98c2c33` |
| Mission 1 camera-role target preflight against sensor-ring endpoint | `artifacts/mission1_camera_target_preflight_20260625/preflight_192_168_16_67_camera_sensor_ring_20260625.json` | `4f963ae01520a00c239b6b9eef5ef5482d2ac71af9ef32e6ec7c1f243166a2bd` |
| Mission 1 latest camera-role target preflight against codex-followup closure build | `artifacts/mission1_camera_target_preflight_20260625/preflight_192_168_16_67_camera_codex_refresh2_20260625.json` | `aee5f3280a56e2e9761383c79708865ce6dca761f5401ff3052a1f2eb477409c` |
| Mission 1 refreshed camera-role target preflight | `artifacts/mission1_camera_target_preflight_20260625/preflight_192_168_16_67_camera_refresh_20260625.json` | `8efcc08e0151b3fccf48d69cba1a8fc2cbdc673c69f97ff1698b8161ac66c3de` |
| Mission 1 latest camera-role target preflight | `artifacts/mission1_camera_target_preflight_20260625/preflight_192_168_16_67_camera_latest_20260625.json` | `96237d3453de87f5addadb40805cebd9e4c7710de11ae8f54198d5ace86c2218` |
| Mission 1 camera-role target preflight against codex-followup closure build | `artifacts/mission1_camera_target_preflight_20260625/preflight_192_168_16_67_camera_codex_followup_20260625.json` | `4fc47baab52433c851b46dc2b62f046812993b1a3409994837dd99b6d6636036` |
| Mission 1 camera-role target preflight after Pi closure build | `artifacts/mission1_camera_target_preflight_20260625/preflight_192_168_16_67_camera_attempt_after_build_20260625.json` | `2452d8f493b77fa51510d3e30baf617abd770a188fe6bedc0c012cdadc8cb0df` |
| Mission 1 stand-in target preflight after Pi closure build | `artifacts/mission1_camera_target_preflight_20260625/preflight_192_168_16_67_standin_after_build_20260625.json` | `94375bc2fba3f31a22c0c018895bd04893e6d61ab15d41d3b325fd9449226a43` |
| Mission 1 camera-side closure package | `artifacts/mission1_camera_closure_package_20260625/closure_package.json` | `186fa95160e1be51667fde1781b3b3243714f9a4265bc4754869a00a9f5d21fa` |
| Mission 1 camera-side closure package Markdown | `artifacts/mission1_camera_closure_package_20260625/closure_package.md` | `d01581d67bee5513750cef9bf7dd3c51c203346bcb3f65c36ed918bdd61d4b00` |
| Mission 1 camera-role closure launch dry-run package | `artifacts/mission1_camera_closure_launch_20260625/mission1_camera_closure_package_dry_run.json` | `7b5c6e6a2ae7e5a32d9994293b194bac8d1b59483ac75bf8dfc4ae00569236f7` |
| Mission 1 host-to-target remote closure launch dry-run | `artifacts/mission1_camera_closure_launch_20260625/mission1_remote_closure_package_dry_run.json` | `dc1b4f9a389a1d70be582f8028cc9f77d9dd18d9d2f229fb0948762071c190fe` |
| Mission 1 real camera-role closure attempt blocked by hardware audit | `artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_20260625/remote_closure_summary.json` | `33a42253a9dfec2ce08e8bdfd6d6d4bd01764b315514d47541a4c7d5b9a35259` |
| Mission 1 real target package stopped at camera hardware audit | `artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_20260625/target_closure_package_run.json` | `46368d523559e76f7f0caadb9215f1c450ac18bc27a4eb514585b1a07662be5f` |
| Mission 1 real camera hardware audit receipt from blocked closure attempt | `artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_20260625/hardware_audit_receipt.json` | `bb3e80419c1fe45b43ac3de682d7459a40bb763fdc900fb443bedf773ac071f6` |
| Mission 1 camera-side closure run | `artifacts/mission1_camera_closure_run_20260625/current_standin/mission1_camera_closure_run.json` | `9bd82f0c081414c1e2d1d49d9de36adfbb182f1021d21ee52efabbc74ef93897` |
| Mission 1 camera-side closure-run target preflight receipt | `artifacts/mission1_camera_closure_run_20260625/current_standin/target_preflight_receipt.json` | `ad48eb6da9a14f7e263dc4c8240638aef857c2f927825fa2bdc11ca5a475be74` |
| Mission 1 camera-side closure-run handoff receipt | `artifacts/mission1_camera_closure_run_20260625/current_standin/camera_handoff_receipt.json` | `515116aa930820ed3c87aefebb33e6df15556070883390bdf5830447e633612b` |
| Mission 1 camera-side closure-run preview UI receipt | `artifacts/mission1_camera_closure_run_20260625/current_standin/preview_ui_receipt.json` | `ccb4c5e78d1e1b244817f025615eb395583c4baa2865cecaa66ab1b90a841e61` |
| Mission 1 follow-up stand-in closure 4K `.gvid` receipt | `artifacts/mission1_camera_closure_run_20260625/current_standin_followup/labs_target_bench.json` | `f2f88db5c272094747f7098a3fc44f667c7c829b2bbd6fe42a931dbed21c2bcf` |
| Mission 1 follow-up stand-in closure target preflight receipt | `artifacts/mission1_camera_closure_run_20260625/current_standin_followup/target_preflight_receipt.json` | `6f9b57025968543ce4fa1e289e6d01e6b134b7ae93526afa2b597f3c8b8ff761` |
| Mission 1 follow-up stand-in closure handoff blocker receipt | `artifacts/mission1_camera_closure_run_20260625/current_standin_followup/camera_handoff_receipt.json` | `c39e40e77b41de5024c5c12a0a38ced4c0c697b9192ba6c46fac1b2920675bc4` |
| Mission 1 follow-up stand-in closure preview receipt | `artifacts/mission1_camera_closure_run_20260625/current_standin_followup/preview_decode_1024x768/receipt.json` | `213650a6b1d2095ce8ab3dbea955065f64d430cfbc691019e9df49c2f1617a4e` |
| Mission 1 follow-up stand-in closure preview UI blocker receipt | `artifacts/mission1_camera_closure_run_20260625/current_standin_followup/preview_ui_receipt.json` | `ef96fd468f0da5dcfbba0b7df0bab519656b9ef5b044e9d29db6e9bbb07b71e7` |
| Mission 1 follow-up stand-in aggregate closure run | `artifacts/mission1_camera_closure_run_20260625/current_standin_followup/mission1_camera_closure_run.json` | `dc2df44aa5ae6a511958640f09d8de963df14616c7ada48861f71ab7956ac5b7` |
| Mission 1 follow-up stand-in aggregate closure collection receipt | `artifacts/mission1_camera_closure_run_20260625/current_standin_followup/collection_receipt.json` | `3129457f3c715b59fe218c9db6a273ae2cd9215ca3111cacb876e648c6fba0b2` |
| Mission 1 current-master handoff bundle manifest | `artifacts/gopro_mission1_handoff_bundle_current_master_20260701/manifest.json` | `252d03ac7ac2aa70031460d6d072441f1e4c7da194d7b127ef231a174dda3a74` |
| Mission 1 current-master handoff bundle checksums | `artifacts/gopro_mission1_handoff_bundle_current_master_20260701/hashes/sha256sums.txt` | `db9c9c01f690914bc7d4b214a46e044dcbcb8dcd3899d62ac656d19617a563bb` |
| Mission 1 current-master handoff bundle sample `.gvid` | `artifacts/gopro_mission1_handoff_bundle_current_master_20260701/samples/mission1_4k_stream_source_8f.gvid` | `95748cda17c78b763be077d4adb6bb3822dd0aecf31353b88680af0bbb9afa9d` |
| Mission 1 current-master handoff bundle archive | `artifacts/gpr-current-master-mission1-handoff-bundle-20260701.tar.gz` | `e56f021ac4de0f4d83cd9235aa846e7d9ecf176afeb4881d374dd5dfd23c1bc7` |
| Mission 1 Pi-target aggregate closure stand-in run | `artifacts/mission1_camera_closure_run_20260625/pi_target_standin_20260625/mission1_camera_closure_run.json` | `53965842670dd65a9fe8e4f7e92459e9c0178fe1de7d0241b116f370a4d00e77` |
| Mission 1 Pi-target aggregate closure target preflight receipt | `artifacts/mission1_camera_closure_run_20260625/pi_target_standin_20260625/target_preflight_receipt.json` | `ad48eb6da9a14f7e263dc4c8240638aef857c2f927825fa2bdc11ca5a475be74` |
| Mission 1 Pi-target aggregate closure handoff receipt | `artifacts/mission1_camera_closure_run_20260625/pi_target_standin_20260625/camera_handoff_receipt.json` | `5df87808f27e61afcb644b926e8a9ad9834c29e2da2c3bf828b7b759d4499380` |
| Mission 1 Pi-target aggregate closure preview UI receipt | `artifacts/mission1_camera_closure_run_20260625/pi_target_standin_20260625/preview_ui_receipt.json` | `ccb4c5e78d1e1b244817f025615eb395583c4baa2865cecaa66ab1b90a841e61` |
| Mission 1 Labs shim Pi stand-in receipt | `artifacts/mission1_labs_shim_pi_standin_20260625/run_120f/labs_target_bench.json` | `5c92b863af08823ba484af1d006aa2de14dcc0d7f01c4b8685f9210fd03c5727` |
| Mission 1 Labs shim Pi stand-in dual receipt | `artifacts/mission1_labs_shim_pi_standin_20260625/run_120f_dual/labs_target_bench.json` | `70facaf64460454766d2f6449c4267c51b4239a808e9567b1d16ae14bd58f955` |
| Mission 1 DMA source simulator profiling receipt | `artifacts/mission1_dma_source_sim_20260628/receipt_4096x3072_60f_20fps.json` | `373c92bede637a8cb01b3d905c6092d2ccdeb97e046daffdfd7fd856d1e8f003` |
| Mission 1 bench_fused DMA-like stream-source 1,440-frame receipt | `artifacts/bench_fused_stream_source_20260628_pi_compact/receipt_4096x3072_1440f_20fps_mmap_ready_fll2_GP017602_replay.json` | `3c6315c0efeb588779550a8fed5fb046ab5f6bf18d73295df20066f2086a1d5d` |
| Mission 1 8K SR production-promotion receipt | `artifacts/mission1_8k_sr_production_promotion_20260625/production_promotion.json` | `1e24b2551d889ced2508d011b77f725a1eb8e855b23a6843127aedc4240db5c9` |
| Mission 1 8K SR visual review package | `artifacts/mission1_8k_sr_visual_review_20260625/visual_review.json` | `52e6a6d896dfc64bb3125dc590d5efa0f110f379ffd60bb1355ff6b9614a7cee` |
| Mission 1 8K SR visual review page | `artifacts/mission1_8k_sr_visual_review_20260625/index.html` | `8a288e7629ca6fedd2adc068d4301aa8ac723fde11a8dca9beae5071152bbcb8` |
| Mission 1 8K SR visual review contact sheet | `artifacts/mission1_8k_sr_visual_review_20260625/visual_review_contact_sheet.jpg` | `a54e3a97538095125e44b8c90241e1cb27e4f9e533234a6179f66c33c6760ac1` |
| Mission 1 step-75 8K SR visual signoff | `artifacts/mission1_8k_sr_coord_detail_psf_focus_step0075_visual_signoff_20260701/visual_signoff.json` | `38ea3d1135909460f22651b747c376d59bad5ac94977a4282ed622e2491de27b` |
| Mission 1 step-75 8K SR signed blocked audit | `artifacts/mission1_8k_sr_coord_detail_psf_focus_step0075_review_candidate_audit_signed_20260701/review_candidate_audit.json` | `29b71f0007e3e8db590b22d7497ecc0eccc056094037b55685a753a86775af1e` |
| Mission 1 8K SR current-candidate editable packaging receipt | `artifacts/mission1_8k_sr_production_promotion_20260625/current_candidate_editable_packaging_frame0/packaging_receipt.json` | `8b96664d71621d27e7ba36f352dbda7fa9d921c86fda60b78068fa75a285fe87` |
| Mission 1 8K SR current-candidate metadata transplant audit | `artifacts/mission1_8k_sr_production_promotion_20260625/current_candidate_metadata_transplant_frame0/metadata_transplant_audit.json` | `abbb3fb8acb109bcb8e4ae5555e3b0451a997ae012ecccfc4441073bcc81b978` |
| Mission 1 all-42 stand-in camera-handoff blocker receipt | `artifacts/mission1_all42_4k_raw_pi20fps_20260624/run_420f_direct_gvid/camera_handoff_receipt.json` | `2db5d44f374c8e19412ceb4c6d4ba2f47d747149d98bf5cdd86e20ffd56917c8` |
| Mission 1 current-source Pi 4K `.gvid` sustained rerun receipt | `artifacts/mission1_current_goal_sync_20260625/run_1440f_direct_gvid/labs_target_bench.json` | `892c5e48f98e3b0e76ecad80dc576e015614cd1f98cecd0d4cb4f23ffc3ad4b1` |
| Mission 1 current-source Pi sustained handoff blocker receipt | `artifacts/mission1_current_goal_sync_20260625/run_1440f_direct_gvid/camera_handoff_receipt.json` | `515116aa930820ed3c87aefebb33e6df15556070883390bdf5830447e633612b` |
| Mission 1 current-source Pi sustained 1024 x 768 preview receipt | `artifacts/mission1_current_goal_sync_20260625/run_1440f_direct_gvid/preview_decode_1024x768/receipt.json` | `74ecef9080f6c8533961c7225a3809d615516fd2a367ab71699bc1076c7c8f68` |
| Mission 1 current-source Pi preview UI blocker receipt | `artifacts/mission1_current_goal_sync_20260625/run_1440f_direct_gvid/preview_ui_receipt.json` | `ccb4c5e78d1e1b244817f025615eb395583c4baa2865cecaa66ab1b90a841e61` |
| Mission 1 4K cleanup objective visual signoff | `artifacts/mission1_4k_cleanup_visual_signoff_20260625/visual_signoff.json` | `6eaf6d1627ddb0b8adaa992d2e050be89631e14bb940165d45fb0a7ed23a8188` |
| Mission 1 4K cleanup visual signoff review page | `artifacts/mission1_4k_cleanup_visual_signoff_20260625/index.html` | `3692a9b5ca9a0d01d78d483a8a6b265672d549bca8d9861a5e1f16d82c4f0a5d` |
| Mission 1 4K cleanup visual signoff contact sheet | `artifacts/mission1_4k_cleanup_visual_signoff_20260625/visual_signoff_contact_sheet.jpg` | `aa0da5393578accf8ecf3337d4c7eeb95d69414a8f93c40073f86a6ab1416b33` |
| Mission 1 4K cleanup high-res CFA production signoff receipt | `artifacts/mission1_4k_cleanup_visual_signoff_20260625/production_signoff.json` | `db690ed64b4e0d9fafef7d49f8fff71625a0350264c0511fef887af488a47f03` |
| candidate-aware 4K cleanup CNN checkpoint (`mission1_native12_4k_cleanup_rgb_cfa_w40_v1`) | `artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/bayer_rgb_target_w40_d5_rs015_gamma2_grad1_raw2_bayer2_step1000.pt` | `baabbd3650c8e09032849e83cfc1526d8a30a47508c55a9a00f5a4e182e16aa1` |
| candidate-aware 4K cleanup CNN training receipt | `artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/bayer_rgb_target_w40_d5_rs015_gamma2_grad1_raw2_bayer2_step1000.pt.json` | `17064271975c8b50e732606d45b81254e0c341470a20ea59c10868ae9d919737` |
| candidate-aware 4K cleanup CNN promotion decision | `artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/mission42_strict_rgb_cfa_candidate_decision.json` | `352eb7986120fda4366ff30bb5bded0d826acfa6170005af6cc6e56031dd5ba9` |
| candidate-aware 4K cleanup RGB/CFA summary | `artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/mission42_rgb_cfa_target_gate_wb_review/summary.json` | `609ac5a1c1ffa0acf5e73cdfea4131bb01287788bb3bbc9ef09e646497a0c317` |
| candidate-aware 4K CNN `.gvid` packaging receipt | `artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/mission42_4k_cnn_gvid_packaging_q8/labs_target_bench.json` | `6b15d0cc2640dbd0b41ea0ec3ad07a561a9331a0a579bcbbdadad147c21c1c86` |
| candidate-aware 4K CNN `.gvid` to 42-frame ProRes receipt | `artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/mission42_4k_cnn_prores_review/receipt.json` | `c6851607113ec37d16b87686db03801d61b43c6bbbf29a4c92ed759d8c827c22` |
| candidate-aware 8K SR Mission42 broad full-frame summary | `artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600/mission42_broad_fullframe/summary.json` | `a5fc58a4d1a6760c87b7365d2a789825fcbaf735523976fa6bd66a9a5c7e950c` |
| candidate-aware 8K SR Z8 broad full-frame summary | `artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600/z8_all24_fullframe/summary.json` | `1021a3fff078a3587476fa0a87691b4502241264057fd1513acff6a5c61b369a` |
| Z8 standalone 8K no-CNN vs CNN review receipt | `artifacts/z8_continuous_8k_no_cnn_vs_cnn_20260630/receipt.json` | `7e15fe6ceee5ac47fe93659132f28608c7633e90afd9f5a2deb416191adec1e9` |
| Z8 standalone 8K no-CNN ProRes review | `artifacts/z8_continuous_8k_no_cnn_vs_cnn_20260630/z8_24f_true_no_cnn_4k_raw_lanczos_to_8k_20p_prores.mov` | `1b441c125e6dc099654a987e9eab716e0bb91b2086dc4038a81d93a0d6fc345c` |
| Z8 standalone 8K CNN ProRes review | `artifacts/z8_continuous_8k_no_cnn_vs_cnn_20260630/z8_24f_with_4k_cleanup_and_8k_sr_cnn_20p_prores.mov` | `6b4f31a87a9fea3c0ed1094fe59120d990987dca903be9bdadf5f6635a909ae0` |
| Mission 1 sequential-scene 8K no-CNN vs CNN review receipt | `artifacts/mission1_8k_scene_GP017497_508_no_cnn_vs_cnn_20260630/receipt.json` | `1aaa3746c485c5427662bfae5c5cb12ec63804464744d47b7708da0f3295608d` |
| Mission 1 sequential-scene 8K no-CNN ProRes review | `artifacts/mission1_8k_scene_GP017497_508_no_cnn_vs_cnn_20260630/GP017497_508_true_no_cnn_8k_12f_20p_prores.mov` | `b9ea593569f7663a995ee7c3bb9d21354c906debd10cbce219e646c401352d3a` |
| Mission 1 sequential-scene 8K CNN ProRes review | `artifacts/mission1_8k_scene_GP017497_508_no_cnn_vs_cnn_20260630/GP017497_508_with_4k_cleanup_8k_sr_cnn_12f_20p_prores.mov` | `ff6a95daaf8378b5e08f78f7c0ff04f19baa488a74dbe38d29310183a16740b2` |
| Mission 1 standalone 8K no-CNN vs CNN review receipt | `artifacts/mission1_8k_true_no_cnn_vs_cnn_20260630/receipt.json` | `a38fbf0370b6ef64fd9175bc8ab114ad9d8f4e03fb55e13a9088b89940e0f0af` |
| Mission 1 standalone 8K no-CNN ProRes review | `artifacts/mission1_8k_true_no_cnn_vs_cnn_20260630/mission42_true_no_cnn_4k_raw_lanczos_to_8k_42f_20p_prores.mov` | `281f9570209baa0b168c2ddbc751aa3164885055cbfefa889d462ee9c984f9c9` |
| Mission 1 standalone 8K CNN ProRes review | `artifacts/mission1_8k_true_no_cnn_vs_cnn_20260630/mission42_with_4k_cleanup_and_8k_sr_cnn_42f_20p_prores.mov` | `78d5edd08d02b82a67de62b91799edf006f217249dbc0822469fc8593f642442` |
| candidate-aware 4K `.gvid` decode-to-8K-SR timing receipt | `artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600/mission42_4kcnn_gvid_to_8k_sr_full42/receipt.json` | `2a5984fc2e99ec80e75a036bf2b509d97fdad475ee548885183d2fd21e756699` |
| candidate-aware 8K SR `.gvid` packaging receipt | `artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600/mission42_4kcnn_8k_sr_gvid_packaging_q3_after_bounds_fix/receipt.json` | `567c62955aa8ccc206d1826c6f2f5b25ba58838e3c7ec5b0f5c9741ab96ce309` |
| candidate-aware 8K SR `.gvid` to 42-frame ProRes receipt | `artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600/mission42_4kcnn_8k_sr_gvid_to_prores_42f_after_bounds_fix/receipt.json` | `895fdf46b04f9e843718995becec46fc87f4da78e136ac897b790208d1153ac1` |
| Mission 4K CNN tone/green-bias audit summary | `artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/mission42_4k_cnn_tone_audit_20260625/summary.json` | `d50c87a98fd9f7831f78bea8b32858ef76bc2cbb7664526c105acbc2e67c5e32` |
| CNN/product scorecard summary | `artifacts/cnn_product_scorecard_20260629/scorecard.json` | `c5915c0a8612d689765caf2f949a07c12a9a04e0506f629867420560e8b87e5a` |
| CNN/product scorecard dashboard | `artifacts/cnn_product_scorecard_20260629/index.html` | `88a76761fb7707c174436ea71af725b6ff043df9fe16f994def48b43d4a85241` |
| SR DNG to ProRes review timebase receipt, not SR throughput | `artifacts/mission1_prores_fps_fix_20260618/prores_fps_fix_receipt.json` | `eb9c9f33f63a53518a88c0a67d72bdeb3ff5fa74d4266e6529485f84a83f8fc1` |
| Stills REF / codec-only / CNN review dashboard | `artifacts/visual_compare_20260525_final/index.html` | `fe7c0926748ac7d421964aef7898c46b232e0f10447f898f07138c5d5c138325` |
| Curated ProRes before/after review manifest | `artifacts/current_goal_prores_before_after_20260619/manifest.json` | `77049fd43508807c598f82a285f5cc63d114f85643c6666d7d52e57bf54a11a8` |
| fresh 8K SR timing receipt | `artifacts/mission1_sr_8k_fresh_bench_20260618/GP017604_mission1_z8_all24_sr_current_t233_lowps_w48_d6_rs03_holdout5_12k_sr8k_512_ov64_bench.json` | `de185d2d8288672966734d1a9078ab729e69b77034121f93f376e374fdfaf0bc` |
| fresh 8K SR full-frame compare | `artifacts/mission1_sr_8k_fresh_bench_20260618/GP017604_holdout5_12k_fullframe_compare.json` | `a2a51f326a9db7d65305359b03c31b3459dba8bb5753b91fa608883339090d09` |
| Mission 1 metadata repack audit | `artifacts/mission1_metadata_audit_refresh_20260618/repacked_profile_fix_audit.json` | `9057b7334da7e17a8caa1439208f9ac768d4701d6bd5d0cb6d6db4c802ccac4b` |
| Mission 1 T233 current-code Pi SSD direct `.gvid` receipt | `artifacts/current_probe_t233_GP017602_pi_20260618/ssd_labs_target_bench.json` | `0cc6d8117e0fbf15acccb8e2fa1512aa05966135551d85d26605456f3de3ddef` |
| Mission 1 T233 current-code Pi SSD-read to SD-write receipt | `artifacts/current_probe_t233_GP017602_pi_20260618/sdwrite_labs_target_bench.json` | `81ecf01ee52518b54c80e045356f2110c6968cc57dbdb926fd72d02dacdb41f6` |
| Mission 1 T233 current-code Pi scatter encode-only stderr | `artifacts/current_probe_t233_GP017602_pi_20260618/encodeonly_scatter_exact.stderr` | `a6c2cbb0f1c0dec6f79df323d8901ac21faf45a76d33e1e238aa7b7a60c028a6` |
| Mission 1 T233 P2 worker-order Pi receipt | `artifacts/current_probe_t233_p2order_GP017602_120f_ssd_20260618_labs_target_bench.json` | `448785f732b701eddd1ceaf1add56d48efff871ac0f63a9b4afff78ab96be682` |
| Mission 1 T233 direct `.gvid` 20 fps metadata receipt | `artifacts/mission1_t233_direct_gvid_fps_metadata_probe_20260618/labs_target_bench.json` | `e16afb224140403d51f58bacd1b143292adc298aa9ad249739071ce8bbb13278` |
| Mission 1 T236 P2 worker-order Pi receipt | `artifacts/current_probe_t236_p2order_GP017602_120f_ssd_20260618_labs_target_bench.json` | `b93dadb8d32b9b0fe9a3ed58159fcab3e0b104d29d9ae19172f1e007dcb5d745` |
| Mission 1 T238 P2 worker-order Pi receipt | `artifacts/current_probe_t238_p2order_GP017602_120f_ssd_20260618_labs_target_bench.json` | `0d77f6fcfb6b0886ffdca9e26bdf0c2353cd9f2732d8d97b74ced8f1dcf5e3f3` |
| Mission 1 T236 left-predictor rejected receipt | `artifacts/current_probe_t236_leftpred_p2order_GP017602_120f_ssd_20260618_labs_target_bench.json` | `72d8615dc584fe0224c0b47194feaedca03bfb1687f87fb279557e4d6094e6f5` |
| Mission 1 T238 left-predictor rejected receipt | `artifacts/current_probe_t238_leftpred_p2order_GP017602_120f_ssd_20260618_labs_target_bench.json` | `869569df8e9bc8e8ba7e27363988da474aae0e3699809c29a299814b5cbcde12` |
| Mission 1 T238 avg/K6555 timing receipt | `artifacts/current_probe_t238_avg_k6555_p2order_GP017602_120f_ssd_20260618_labs_target_bench.json` | `835185debe5722e55b1efceddf9826c3f54ec2156249179f57ea21d673f7d1c3` |
| Mission 1 T238 avg/K6555 ping-pong rejected receipt | `artifacts/current_probe_t238_avg_k6555_pingpong_GP017602_120f_ssd_20260618_labs_target_bench.json` | `52db32b1b451165724bbb0d269f44eebc414ba568850d5d59ac4fad61b8bdf0e` |
| Mission 1 T238 avg/K6555 async-writer rejected receipt | `artifacts/current_probe_t238_avg_k6555_async_GP017602_120f_ssd_20260618_labs_target_bench.json` | `d92b0808f73c2ec8056ad650db9ab8f40a192a02405534c5a53ab0f05063d64f` |
| Mission 1 T238 avg/K6555 `-Ofast` rejected receipt | `artifacts/current_probe_t238_avg_k6555_ofast_p2order_GP017602_120f_ssd_20260618_labs_target_bench.json` | `43c3dfc4c5afeb4a7873905c9274a4ef599de1d67631bcbadfe9138641dfca2e` |
| Mission 1 rejected scalar-JANS Pi receipt | `artifacts/current_probe_t236_scalarjans_p2order_GP017602_60f_ssd_20260618_labs_target_bench.json` | `44df87ee99aad1933bae10464824d172c8430a095648de945e8ceca933d67da7` |
| Mission 1 T233 fresh strict-24 target refresh | `artifacts/current_goal_refresh_t233_GP017602_120f_24fps_20260618/labs_target_bench.json` | `179a4e18c34fcff68290ae5373a3390a5017b9f603ecb8d8a65ca5f514ef088e` |
| Mission 1 T233 fresh timing-detail target refresh | `artifacts/current_goal_timingdetail_GP017602_24f_20260618/labs_target_bench.json` | `26c1e88ee728ef9b064886abc9e4a6aa319ff61a6667128d770c2ddb72987d64` |
| Mission 1 LL K sweep `7,6,5,5` receipt | `artifacts/current_goal_llk_sweep_7_6_5_5_GP017602_24f_20260618/labs_target_bench.json` | `1509c130760d6d67448d750e0c3948e0a84adccfb289bb2a0e77721c90619d96` |
| Mission 1 LL K sweep `7,6,6,6` receipt | `artifacts/current_goal_llk_sweep_7_6_6_6_GP017602_24f_20260618/labs_target_bench.json` | `24c66e4d2261c3e5cc8ad67fc432b261f62d8693779317d3431b0f722fca9396` |
| Mission 1 LL K sweep `8,5,5,5` receipt | `artifacts/current_goal_llk_sweep_8_5_5_5_GP017602_24f_20260618/labs_target_bench.json` | `b455d810545ab68a3cb424e5aaed437127cbc75fdedd77abfb3621ccacd76ca3` |
| Mission 1 LL K sweep `8,6,6,6` receipt | `artifacts/current_goal_llk_sweep_8_6_6_6_GP017602_24f_20260618/labs_target_bench.json` | `6a521a3745e819b299ce4cf034a2bbb4f21db42439f4451f2470169fcdef0ccb` |
| Mission 1 T356 SR pair-builder smoke NPZ | `artifacts/current_goal_sr_pair_profile_smoke_t356_20260618/t356_pair_smoke.npz` | `71d32f86a791fa1be0fb7e42137323a259c510d7a7885d76db57c4bffd17ae4b` |
| Mission 1 T356 SR pair-builder smoke metadata | `artifacts/current_goal_sr_pair_profile_smoke_t356_20260618/t356_pair_smoke.npz.json` | `4aed9e9500bfd8b6fb64aba35e5c43f201b8762bcb0c2094255b696646b29ad2` |
| Mission 1 T356 SR training pairs | `artifacts/mission1_sr_t356_ch2lh3_20260618/mission1_sr_pairs_t356_ch2lh3_gaussian_area_96t_w96.npz` | `165ddbce12952a672c87b27066742c0692dfac6311e3a0afadc07a8dcbe2deb9` |
| Mission 1 T356 SR training metadata | `artifacts/mission1_sr_t356_ch2lh3_20260618/mission1_sr_pairs_t356_ch2lh3_gaussian_area_96t_w96.npz.json` | `253bc6d675553fa85b5a6d06d018ae6488064315dfb324ab049d31ebdd05c521` |
| Mission 1 T356 SR 4k-step checkpoint | `artifacts/mission1_sr_t356_ch2lh3_20260618/mission1_sr_t356_ch2lh3_from_t233_w48_d6_rs03_holdout604_4k.pt` | `0d957ca98026702ca01d44e4f0008d4037601790667e177a4a87247e278c926c` |
| Mission 1 T356 SR 4k-step training receipt | `artifacts/mission1_sr_t356_ch2lh3_20260618/mission1_sr_t356_ch2lh3_from_t233_w48_d6_rs03_holdout604_4k.pt.json` | `1962cae61647a0d9f8f236912013582839698004b72d7e77487ed090a0c67277` |
| Mission 1 T356 SR extended checkpoint | `artifacts/mission1_sr_t356_ch2lh3_20260618/mission1_sr_t356_ch2lh3_from_4k_w48_d6_rs03_holdout604_8kmore.pt` | `73c6798c0bb1c9182e5f64e3723815f6cc103ab252d68fcddcabb2081f35ab17` |
| Mission 1 T356 SR extended training receipt | `artifacts/mission1_sr_t356_ch2lh3_20260618/mission1_sr_t356_ch2lh3_from_4k_w48_d6_rs03_holdout604_8kmore.pt.json` | `22d5447ad424452d7dc07e5f680cbddfe2db9ee47453430f51446f5acb440f9c` |
| Mission 1 T356 SR held-out full-frame summary | `artifacts/mission1_sr_t356_holdout604_fullframe_8kmore_20260618/summary.json` | `9626116beb89b14f3f877c95f4d93942cd420340feaa756ab0229eaf25812583` |
| Mission 1 T356 SR held-out full-frame compare | `artifacts/mission1_sr_t356_holdout604_fullframe_8kmore_20260618/GP017604/GP017604_fullframe_compare.json` | `1ea7bff3b12cc90c41ab1f14a3a73f43ed8c2dd96a6f656cb1270e1009461eac` |
| Mission 1 T356 SR held-out 8K timing receipt | `artifacts/mission1_sr_t356_holdout604_fullframe_8kmore_20260618/GP017604/GP017604_mission1_sr_t356_ch2lh3_from_4k_w48_d6_rs03_holdout604_8kmore_sr8k_512_ov64_bench.json` | `00165dd9c900ac55dc7f2dad77e9a11d579df41f11a9c33167bd3d111b83ec59` |
| Mission 1 T356 SR broad-holdout checkpoint | `artifacts/mission1_sr_t356_ch2lh3_20260618/mission1_sr_t356_ch2lh3_from_t233_w48_d6_rs03_holdout8_8k.pt` | `a4428f49a9e7d076280e63eb7d88ab094906a0c87292e271332116d6f0f8b3c8` |
| Mission 1 T356 SR broad-holdout training receipt | `artifacts/mission1_sr_t356_ch2lh3_20260618/mission1_sr_t356_ch2lh3_from_t233_w48_d6_rs03_holdout8_8k.pt.json` | `1408c3189365546103fbf1e68ef6a699d57329f3ddf09eef02561e2af56d7175` |
| Mission 1 T356 SR broad full-frame summary | `artifacts/mission1_sr_t356_holdout8_fullframe_20260618/summary.json` | `e3cad9de95d50471e2e050f2e302e8c8eeff5a6fb6ab68d576ef7fb7d7d6661b` |
| Mission 1 T356 SR broad worst-frame compare | `artifacts/mission1_sr_t356_holdout8_fullframe_20260618/GP017349/GP017349_fullframe_compare.json` | `73dedf2b2019dd9f6fdd2dac007c3e1f22578191a9991ecfe658216d8857f7e8` |
| Mission 1 T356 SR broad worst-frame timing receipt | `artifacts/mission1_sr_t356_holdout8_fullframe_20260618/GP017349/GP017349_mission1_sr_t356_ch2lh3_from_t233_w48_d6_rs03_holdout8_8k_sr8k_512_ov64_bench.json` | `6f6e434a8cef6626551569a3b004184c3d562a4601531a33bb85ab85bf2f78c0` |
| Mission 1 T236 SR training pairs | `artifacts/mission1_sr_t236_ch2lh3_20260618/mission1_sr_pairs_t236_ch2lh3_gaussian_area_96t_w96.npz` | `f8927f3b6cc36bf367627b1c15f1b780732f53ac8ad747e43a750739778383e7` |
| Mission 1 T236 SR training metadata | `artifacts/mission1_sr_t236_ch2lh3_20260618/mission1_sr_pairs_t236_ch2lh3_gaussian_area_96t_w96.npz.json` | `b93000b84a450f43448dcb0528921c4d536c1942a6a46b60ab0488ca84392dbe` |
| Mission 1 T236 SR broad-holdout checkpoint | `artifacts/mission1_sr_t236_ch2lh3_20260618/mission1_sr_t236_ch2lh3_from_t233_w48_d6_rs03_holdout8_8k.pt` | `0976097d53e383a932e3eec29a307be1ec188f8b295edd699ed882ddf182e3d7` |
| Mission 1 T236 SR broad-holdout training receipt | `artifacts/mission1_sr_t236_ch2lh3_20260618/mission1_sr_t236_ch2lh3_from_t233_w48_d6_rs03_holdout8_8k.pt.json` | `af04416c15189ba2262334988ff338e7919dea4e86e244bc07fd478129b909fa` |
| Mission 1 T236 SR broad full-frame summary | `artifacts/mission1_sr_t236_holdout8_fullframe_20260618/summary.json` | `3d93fa8b82740a91061d8c36c44044656079659178685304635fa38f0ea690be` |
| Mission 1 T236 SR broad worst-frame compare | `artifacts/mission1_sr_t236_holdout8_fullframe_20260618/GP017349/GP017349_fullframe_compare.json` | `29f1426ac9a1a4a116ff161f0f83a1cf781630c10c540958e101067d62582f79` |
| Mission 1 T236 SR broad worst-frame timing receipt | `artifacts/mission1_sr_t236_holdout8_fullframe_20260618/GP017349/GP017349_mission1_sr_t236_ch2lh3_from_t233_w48_d6_rs03_holdout8_8k_sr8k_512_ov64_bench.json` | `d094874f48ea4e985faed03c8ac29ed5caa6e2b59a0fc10d35405de8b52ae896` |
| Mission 1 T236 SR broad gradient-weight checkpoint | `artifacts/mission1_sr_t236_ch2lh3_20260618/mission1_sr_t236_ch2lh3_from_8k_w48_d6_rs03_gw08_holdout8_6kmore.pt` | `c3a43aa072b2e44bf2f17e94f255f349e01d60a56358c57d40d5c005b5ef5e54` |
| Mission 1 T236 SR broad gradient-weight training receipt | `artifacts/mission1_sr_t236_ch2lh3_20260618/mission1_sr_t236_ch2lh3_from_8k_w48_d6_rs03_gw08_holdout8_6kmore.pt.json` | `4656c32c8d2fc9b87611832c08797b6315302d9d7c2bc69c5aced6e235dee156` |
| Mission 1 T236 SR broad gradient-weight summary | `artifacts/mission1_sr_t236_gw08_holdout8_fullframe_20260618/summary.json` | `198374acbd38a7c101964d99693fae06a471be111f8a6b5bfefb5b4a31ac651f` |
| Mission 1 T236 SR broad gradient-weight worst-frame compare | `artifacts/mission1_sr_t236_gw08_holdout8_fullframe_20260618/GP017349/GP017349_fullframe_compare.json` | `bb389ea40940d4344c4da1bfff052e5fc39db04e3c075b63d8946bd180b51a7f` |
| Mission 1 T236 SR broad gradient-weight worst-frame timing receipt | `artifacts/mission1_sr_t236_gw08_holdout8_fullframe_20260618/GP017349/GP017349_mission1_sr_t236_ch2lh3_from_8k_w48_d6_rs03_gw08_holdout8_6kmore_sr8k_512_ov64_bench.json` | `01d14ec158e881ab2e368fc69b6f86463490f8ee7f05119656ea89d32b751918` |
| Mission 1 T233 focused hard-row SR checkpoint (`mission1_native12_8k_sr_focus_hardrows_2500_v1`) | `artifacts/mission1_sr_t233_focus_hardrows_20260618/mission1_sr_t233_focus_gp017346_gp017349_from_registered_w48_d6_rs03_2500.pt` | `c2e08917bcd32049ce9971de2fe694d4d13fe46ae0392b85d6eac534c5d7bd13` |
| Mission 1 T233 focused hard-row SR training receipt | `artifacts/mission1_sr_t233_focus_hardrows_20260618/mission1_sr_t233_focus_gp017346_gp017349_from_registered_w48_d6_rs03_2500.pt.json` | `a5807cee8faa7dfd6073cd9644e88b26ed82753b4a5787afb382b08f905ffb92` |
| Mission 1 T233 focused hard-row broad summary | `artifacts/mission1_sr_t233_focus_hardrows_fullframe_holdout8_20260618/summary.json` | `2dbd0c785c8df7d09542a54fbed2e1fe9e128ebb40e1780f591454a04e3346aa` |
| Mission 1 T233 focused hard-row regenerated Z8 summary | `artifacts/mission1_sr_t233_focus_hardrows_z8_holdout5_fullframe_20260618/summary.json` | `d6173273e36953ab41ec19f03d68a837f416f57586734c75534a2e3e2a4cb581` |
| Mission 1 T233 registered regenerated Z8 comparison summary | `artifacts/mission1_sr_t233_registered_z8_holdout5_regen_fullframe_20260618/summary.json` | `bf7d1e5c8e52022ffbe31421e078b8fc321368da97b91fa070e9b21d329caf63` |
| Mission 1 regenerated Z8 holdout metadata | `artifacts/mission1_z8_holdout5_current_t233_regen_20260618/z8_holdout5_current_t233_probe_pairs.npz.json` | `096e155e8fdfb52125a2d6ad0eb769a182d1fee8cd9729d3c36a4e43ffde2da7` |
| Mission 1 T233 focused hard-row registry `.gvid` SR smoke | `artifacts/mission1_native12_gvid_to_8k_sr_focus_registry_smoke_20260618/receipt.json` | `768910083ca2f17b6ba293a25f6fc6e9c22c29a32b6d5ac82b79d9a18838ffa8` |
| Mission 1 T233 focused hard-row multi-frame `.gvid` SR receipt | `artifacts/mission1_native12_gvid_to_8k_sr_focus_multiframe_20260618/receipt.json` | `e2eef3b216b42cbfe3bdc5195992b5df34109b43b456e376e491e987362cca5d` |
| Mission 1 T233 focused hard-row retained SR render receipt | `artifacts/mission1_native12_gvid_to_8k_sr_focus_packaging_20260618/receipt.json` | `03222ad9af3c5c60ad16df45bcc284f7af17dca81bf4c1b2135eaf89ea347ab4` |
| Mission 1 T233 focused hard-row packaging receipt | `artifacts/mission1_native12_gvid_to_8k_sr_focus_packaging_20260618/packaging_receipt.json` | `585d902c4d20f41ddd529658dbbc554d90ae09eaa750707d45ff597c7362e5d1` |
| Mission 1 T233 guardrail-focus SR checkpoint (`mission1_native12_8k_sr_guardrail_focus_1500_v1`) | `artifacts/mission1_sr_t233_guardrail_focus_20260618/mission1_sr_t233_guardrail_focus_from_focus_w48_d6_rs03_1500.pt` | `9a8ce5c936da1ae26823b1ce613aabb510e7c124004fa2b5b786a69ba74d7508` |
| Mission 1 T233 guardrail-focus SR training receipt | `artifacts/mission1_sr_t233_guardrail_focus_20260618/mission1_sr_t233_guardrail_focus_from_focus_w48_d6_rs03_1500.pt.json` | `fef6bc6759607ac0fc3eb6d7ff18b32a35064d322c778d311592dc6e55216814` |
| Mission 1 T233 guardrail-focus broad summary | `artifacts/mission1_sr_t233_guardrail_focus_fullframe_holdout8_20260618/summary.json` | `089468cc997cd336eb4b4725b46116a713e0a90b21c5c3b82521c731dbfc2cd6` |
| Mission 1 T233 guardrail-focus regenerated Z8 summary | `artifacts/mission1_sr_t233_guardrail_focus_z8_holdout5_fullframe_20260618/summary.json` | `e19a3b09677bf35ff68cee8ee9c7cc9c4a382162cdef6d3041b3b2572c484054` |
| Mission 1 T233 1x/2x CNN review dashboard summary | `artifacts/current_goal_cnn_1x2x_review_20260618/summary.json` | `b07d823b6d440638879dbf3caaa5203a636b10b4238508763f5526728964f7e0` |
| Mission 1 native detail-residual sidecar thread sweep | `artifacts/current_goal_sr_detail_residual_native_sidecar_threads_20260619/summary.json` | `911944f7f9b55f43b134314e140f79134874a776d6faae53acf7e9c0773d8aef` |
| Mission 1 native compact detail-residual sidecar sweep | `artifacts/current_goal_sr_detail_residual_native_sidecar_compact_20260619/summary.json` | `a0a64f78fda353eee405a7d523b02108b16da4d302f0e5d7568dd7f2a21c43c3` |
| Mission 1 native direct compact detail-residual sidecar sweep | `artifacts/current_goal_sr_detail_residual_native_sidecar_compact_direct_20260619/summary.json` | `2532c972ab3eb7c7b2a1ff4af568ace9af55b5749e299c690737ad7e0e2f6569` |
| Mission 1 detail-residual sidecar Pareto sweep | `artifacts/current_goal_sr_detail_residual_pareto_20260619/pareto_summary.json` | `1a9cf3e12b731f4b19d6183424ac186d48158732f16b71164b0b1f619d9c22f5` |
| Mission 1 detail-residual q3/t1 focus budget | `artifacts/current_goal_sr_detail_residual_pareto_20260619/mission_focus8_q3_t1_all_budget.json` | `f0d8868669c6cae144c724f60411014a21c7f2af3fe1be53da8702194aaac250` |
| Z8 detail-residual q3/t1 holdout budget | `artifacts/current_goal_sr_detail_residual_pareto_20260619/z8_holdout5_q3_t1_all_budget.json` | `84fc958c7394f982241ebd5879ea2d7705cf1b30c71ba3ebae68160a6abaed4c` |
| Mission 1 native q3/t1 direct compact detail-residual sidecar sweep | `artifacts/current_goal_sr_detail_residual_native_sidecar_q3t1_direct_20260619/summary.json` | `61f9f2e4e373f707c864d61a205ef467913ddb6c9bfb769eb7000bf0ac5f1223` |
| Mission 1 native q4/t2 direct compact detail-residual sidecar sweep | `artifacts/current_goal_sr_detail_residual_native_sidecar_q4t2_direct_20260619/summary.json` | `62fc817a3fc13eaa728683857758391e6b8306717c3b4fcdeacc1c83e656803c` |
| Mission 1 q3/q4 detail-residual SR hard-row gate summary | `artifacts/current_goal_sr_detail_residual_q3q4_sr_gate_20260619/summary.json` | `5e1ecb4125bcd7c2b6f8fcb11a8b97794b02192400e7b395e762cb1b47c2c408` |
| Mission 1 q4/t2 detail-residual SR hard-row gate | `artifacts/current_goal_sr_detail_residual_q3q4_sr_gate_20260619/q4_t2_all/preclean_step0200_hard3_fullframe/summary.json` | `181c388491ff9073d34ce1bf838e73955272db101b63873c3928cceb21c38b8f` |
| Mission 1 q4/t2 detail-residual broad Mission42/Z8 SR gate summary | `artifacts/current_goal_sr_detail_residual_q4t2_broad_gate_20260619/summary.json` | `3edc2ea7a7f00ab1d03f5ad2c7de8eb8b66e4b3ef7fc1e228f4d65d21d29065d` |
| Mission 1 q4/t2 detail-residual broad Mission42 SR gate | `artifacts/current_goal_sr_detail_residual_q4t2_broad_gate_20260619/mission42_q4_t2_all/preclean_step0200_fullframe/summary.json` | `a4630414fc3b4fa42a612ce9c8078e2ecdf42a46b418e6eb0de706ddb0ac59d8` |
| Z8 all24 q4/t2 detail-residual broad SR gate | `artifacts/current_goal_sr_detail_residual_q4t2_broad_gate_20260619/z8_all24_q4_t2_all/preclean_step0200_fullframe/summary.json` | `cf98bbbaba5d63df14646ca7981a7c74441a90e6c5c1161f80075ad91542d493` |
| Z8 all24 high-target raw manifest for q4/t2 broad SR gate | `artifacts/current_goal_sr_detail_residual_q4t2_broad_gate_20260619/z8_all24_high_target_raw/manifest.json` | `e954a8dc589bc3010ca0a2d5b9d141915d7f0de69df9f6c1212ecdb4d1d20162` |
| Mission+Z8 q4/t2 sidecar-aware SR training pairs (`mission1_native12_8k_sr_q4t2_sidecar_aware_s400_v1` `training_pairs_path`) | `artifacts/current_goal_sr_q4t2_sidecar_aware_train_20260619/mission42_z8_all24_q4t2_inputs_w96.npz` | `d6976cbf92729b78eeff7bf0c6b0f79e550c7d895bd64a7db21a61a0e9526d62` |
| Mission+Z8 q4/t2 sidecar-aware SR training pair sidecar | `artifacts/current_goal_sr_q4t2_sidecar_aware_train_20260619/mission42_z8_all24_q4t2_inputs_w96.npz.json` | `729bc9db246352eace0db93407f8b5d8ceee66deb1744d0b3699db1f20b54910` |
| Mission+Z8 q4/t2 sidecar-aware SR registry-review checkpoint (`mission1_native12_8k_sr_q4t2_sidecar_aware_s400_v1` `ckpt_path`) | `artifacts/current_goal_sr_q4t2_sidecar_aware_train_20260619/sidecar_aware_preclean_step0200_continue_s400/q4t2_sidecar_aware_preclean_continue_s400.pt` | `a16579f2aacd6edbadc3931ab112a3ff52566bd4f8a6245c95b246b16af98bb5` |
| Mission+Z8 q4/t2 sidecar-aware SR training receipt | `artifacts/current_goal_sr_q4t2_sidecar_aware_train_20260619/sidecar_aware_preclean_step0200_continue_s400/q4t2_sidecar_aware_preclean_continue_s400.pt.json` | `9b20c909e5a48f376933a81a9de26cf21223b05d20ec7f8f46b541d9a907018b` |
| Mission+Z8 q4/t2 sidecar-aware SR guarded decision | `artifacts/current_goal_sr_q4t2_sidecar_aware_train_20260619/sidecar_aware_preclean_step0200_continue_s400/q4t2_sidecar_aware_preclean_continue_s400_decision.json` | `660f22cf85c392b9e43d7ce5f525fa5f4450f51905f3629934ee48a18f1d850b` |
| Mission+Z8 q4/t2 sidecar-aware SR guarded summary | `artifacts/current_goal_sr_q4t2_sidecar_aware_train_20260619/sidecar_aware_preclean_step0200_continue_s400/guarded_experiment_summary.json` | `2635796d17f7559ca79a0c1fe39d7eeff3f019aa0b05e38e91b71215de52b5ce` |
| Mission42 q4/t2 sidecar-aware SR full-frame summary | `artifacts/current_goal_sr_q4t2_sidecar_aware_train_20260619/sidecar_aware_preclean_step0200_continue_s400/q4t2_sidecar_aware_preclean_continue_s400_mission_fullframe/summary.json` | `7a0c23293336fc52e246aed4f3cff5aee26f787c97a724239c2fdb282fd1330d` |
| Z8 all24 q4/t2 sidecar-aware SR full-frame summary | `artifacts/current_goal_sr_q4t2_sidecar_aware_train_20260619/sidecar_aware_preclean_step0200_continue_s400/q4t2_sidecar_aware_preclean_continue_s400_z8_fullframe/summary.json` | `a18e5c14a9d5c96727d86fa492e5c06ae19b4a4123c84438345c7b66e233174a` |
| Mission+Z8 q4/t2 sidecar-aware `.gvid` multi-frame SR receipt | `artifacts/mission1_native12_gvid_to_8k_sr_q4t2_sidecar_aware_multiframe_20260619/receipt.json` | `b79cac5b1ad12bdeeddac0bb4b53bc806b45c5822fb6ac6fe1267f5d4a6501d1` |
| Mission+Z8 q4/t2 sidecar-aware retained SR render receipt | `artifacts/mission1_native12_gvid_to_8k_sr_q4t2_sidecar_aware_packaging_20260619/receipt.json` | `9bd45a49a13b344498907f7c0532a120fff2944382a9659bd1db9870f39d2e57` |
| Mission+Z8 q4/t2 sidecar-aware q3 packaging receipt | `artifacts/mission1_native12_gvid_to_8k_sr_q4t2_sidecar_aware_packaging_q3_20260619/packaging_receipt.json` | `eab82ddaa985e2ce6f1667ee5ad025f60a87fc8ee4d4e83504a3121e5975c8f8` |
| Mission+Z8 rejected q4/t2 sidecar-aware checkpoint interpolation decision | `artifacts/current_goal_sr_q4t2_sidecar_aware_interp_probe_20260619/interpolation_decision_summary.json` | `8b6972e2cb4dfecb05c0c89229e029c1647a06276c7937da3f9fae497c01b8da` |
| Mission+Z8 q4/t2 sidecar-aware SR production gap report | `artifacts/current_goal_sr_production_gap_report_20260619/summary.json` | `9cde420dbdd5ebbf93bacd8a416fbec5fc7f33eb53ef26b0a3bb3fbd06f51df9` |
| Mission 1 T233 guardrail-focus registry `.gvid` SR smoke | `artifacts/mission1_native12_gvid_to_8k_sr_guardrail_registry_smoke_20260618/receipt.json` | `fd515841b82b2055e84a3270c2bd63dff12beaecb994a701b8a642e8d8544cc7` |
| Mission 1 T233 guardrail-focus multi-frame `.gvid` SR receipt | `artifacts/mission1_native12_gvid_to_8k_sr_guardrail_multiframe_20260618/receipt.json` | `9fd6d2405181989ebb1b854fb40d853e88bd5d0fd2e17100027ec73bd47e1f06` |
| Mission 1 T233 guardrail-focus retained SR render receipt | `artifacts/mission1_native12_gvid_to_8k_sr_guardrail_packaging_20260618/receipt.json` | `fdc32724aa7394f14ee738af77cd882220717242f15aeca7b113219cded8f6ec` |
| Mission 1 T233 guardrail-focus q5 packaging receipt | `artifacts/mission1_native12_gvid_to_8k_sr_guardrail_packaging_q5_20260618/packaging_receipt.json` | `756ad891366c40e8126ff11e783541a08972a0f6fd194e20c05cf6dacc56c500` |
| Mission 1 T233 guardrail-light SR checkpoint (`mission1_native12_8k_sr_guardrail_light_w15_800_v1`) | `artifacts/mission1_sr_t233_guardrail_light_w15_800_20260618/mission1_sr_t233_guardrail_light_w15_from_focus_w48_d6_rs03_800.pt` | `5994b69f74f3df228730d523663a02ebd12251fe5f636a0b7894638a7d823e98` |
| Mission 1 T233 guardrail-light SR training receipt | `artifacts/mission1_sr_t233_guardrail_light_w15_800_20260618/mission1_sr_t233_guardrail_light_w15_from_focus_w48_d6_rs03_800.pt.json` | `643594072391dceac5237e01887889d9e358be5ca447bd92a23b310a79f4c3f3` |
| Mission 1 T233 guardrail-light broad summary | `artifacts/mission1_sr_t233_guardrail_light_w15_800_fullframe_holdout8_20260618/summary.json` | `2a6dbd9b9d4cb28974cf926d3fc4d405436316a422e0e3711753eab4b4497633` |
| Mission 1 T233 guardrail-light regenerated Z8 summary | `artifacts/mission1_sr_t233_guardrail_light_w15_800_z8_holdout5_fullframe_20260618/summary.json` | `cf862709762442927703b1b45df316013a0b16c8aa61257da6ad20b67b22666f` |
| Mission 1 T233 guardrail-light multi-frame `.gvid` SR receipt | `artifacts/mission1_native12_gvid_to_8k_sr_light_multiframe_20260618/receipt.json` | `8f663b1e3ece579885dcc5872dd91b0fbf545facdae5e939b546c0455c2a1172` |
| Mission 1 T233 guardrail-light retained SR render receipt | `artifacts/mission1_native12_gvid_to_8k_sr_light_packaging_20260618/receipt.json` | `06090968f24197318c99789322e6ce251147cc2274bde050cbddc2d7c914eeb1` |
| Mission 1 T233 guardrail-light q3 packaging receipt | `artifacts/mission1_native12_gvid_to_8k_sr_light_packaging_q3_20260618/packaging_receipt.json` | `25aadd4b4b9b8c63b820348c7907a4f65ff0e1970e25096e63c5daab71ed0629` |
| Mission 1 T233 guardrail-light wrapper probe | `artifacts/mission1_native12_gvid_to_8k_sr_light_wrapper_probe_20260618/summary.json` | `94abf0e0d7f23e2d4619fa8d2b74037f6984d1ccc334bb687e86263bc8f346d7` |
| Mission 1 preclean-aux broad SR candidate (`mission1_native12_8k_sr_preclean_aux_broad_step0200_v1`) | `ckpt_path`: `artifacts/current_goal_sr_preclean_aux_broad_recovery_20260618/eval_checkpoints/preclean_aux_broad_recovery_w96_d6_rs03_gw08_lap01_aux05_1600_step000200.pt` | `2d59331bc7ae5561c74388006e0405deda4f392b386b90ad4d05066a86d91da2` |
| Mission 1 preclean-aux broad SR training pairs (`mission1_native12_8k_sr_preclean_aux_broad_step0200_v1`) | `training_pairs_path`: `artifacts/current_goal_sr_current_contract_hardfocus_merged_20260618/mission42_z8_plus_hard2_current_contract_t233_gaussian_area_w96.npz` | `7ff4c956d992a425bf39b1b78b85e25f06b8df2227ca0c45d8e023792e7311c2` |
| Mission 1 native12 SR frontier summary | `artifacts/mission1_native12_sr_frontier_summary_20260618/summary.json` | `ec65cb26252ae7525a7fe33e473507bc3a9c00219940697f9f776d8ec12dbe3a` |
| Mission 1 rejected T233 guarded-focus SR decision | `artifacts/current_goal_sr_t233_guarded_focus_w8_600_decision_20260618/decision.json` | `1a3c532e9dc2a9bf27d3a2a4b4172144f1ad92e96c0556420efe2d30ad0aaefb` |
| Mission 1 rejected mixed Mission+Z8 guarded SR probe | `artifacts/current_goal_sr_guarded_mixed_probe_20260618/guarded_experiment_summary.json` | `0f9eed3dc9834e8ac9b571e2bbcfb00a5dd15f80349df2969b6f05567e26f6d4` |
| Mission 1 rejected full-coverage mixed Mission+Z8 guarded SR probe | `artifacts/current_goal_sr_guarded_mixed_probe_20260618/guarded_experiment_fullcoverage_summary.json` | `d8f1ed445b36b2c1f38574aaedee38b6e5b67d3163c7c3c078611bed088ca5a0` |
| Mission 1 rejected random-start resblock SR guarded probe | `artifacts/current_goal_sr_resblock_probe_20260618/guarded_experiment_summary.json` | `1380b57b7b2f8f61592adfe6d383c92f1471f54a2588ab7083ded321eb48094a` |
| Mission 1 rejected zero-init resblock SR guarded probe | `artifacts/current_goal_sr_resblock_zeroinit_probe_20260618/guarded_experiment_summary.json` | `3453ecb72657eeeb57cb81272579f458a9a6aab59fc275e7bb68307948fd3d4c` |
| Mission 1 rejected production-sized zero-init resblock SR guarded probe | `artifacts/current_goal_sr_resblock_zeroinit_w48_800_probe_20260618/guarded_experiment_summary.json` | `c151c2c24917aa1d7876221bbc386ca9c426c5022c18d659c0f9d9bc882d9a41` |
| Mission 1 rejected light-focus SR checkpoint interpolation probe | `artifacts/current_goal_sr_interp_light_focus_probe_20260618/summary.json` | `d21aae4ffd31af040e9a2270904625c40c16f04195e484b24d2a46ac3e885176` |
| Mission 1 current 100% review dashboard | `artifacts/mission1_current_review_100pct_dashboard_20260618/index.html` | `b8492487ca108afde8a0b486db99e363e8417f9ad2dc9c36b5eee368e8b315a4` |
| Mission 1 current 100% review summary | `artifacts/mission1_current_review_100pct_dashboard_20260618/summary.json` | `725e658d4aefdfdd6cd87a535e6b2bb33f256a396cb57eeb4cc3bd6712963106` |
| Mission 1 native12 frontier summary | `artifacts/mission1_native12_frontier_summary_20260618/summary.json` | `df935269fc98e21c91f49a3e9390839b8a5af553a0036c283a0fe4f92277d4c6` |
| Mission 1 native12 tokenizer baseline microbench | `artifacts/mission1_prod_jans_coeff_stats_splitdump_20260617/jans_coeff_bench_highpass_summary.json` | `0c502290b31c7c7ed497748ca8705d40bb0baced9dffd5433901eda13b9ce9f0` |
| Mission 1 rejected native12 tokenizer mag4 microbench | `artifacts/mission1_prod_jans_mag4fast_splitdump_20260617/jans_coeff_bench_highpass_summary.json` | `43a04203798962bf5804274a436ff2d09ef1d6e2606c9f5d475aed7068ac273e` |
| Mission 1 rejected native12 tokenizer packed-LUT microbench | `artifacts/mission1_prod_jans_packedlut_splitdump_20260617/jans_coeff_bench_highpass_summary.json` | `4259a8579bc4472ee1e5d2df4bf3cc719e1af5b6b63db3b63043365ee2bb9c50` |
| Mission 1 rejected native12 tokenizer packed-LUT Pi receipt | `artifacts/mission1_prod_jans_packedlut_GP017602_120f_24fps_20260617/labs_target_bench.json` | `dc4e15c84ecfec4c9fdf7a8c4bcd78a45fe235df5c9ec970ce330b5ac4afd1e6` |
| Mission 1 rejected native12 tokenizer zero-scan summary | `artifacts/mission1_jans_zero_scan_probe_20260618/summary.json` | `5f790bcb80d7cf526208042e4b3e2017dfb371f62407374fb7cca3c90f8cc32b` |
| Mission 1 rejected native12 tokenizer prefetch summary | `artifacts/current_goal_jans_prefetch_probe_20260618/summary.json` | `4f9a2166b11405ebab43a0c4f347e182a7bac8711ecc0a2fcd912bea04236dbd` |
| Mission 1 rejected native12 tokenizer prefetch Pi receipt | `artifacts/current_goal_jans_prefetch64_t236_GP017602_60f_20260618/labs_target_bench.json` | `66ba75312581930e3e34ae88a1c5015f1a78c189cd382c131ddb26d1a04e6321` |
| Mission 1 native12 unpack timing-detail receipt | `artifacts/mission1_unpack_asm_pass_20260617/timing_detail_GP017602_30f/labs_target_bench.json` | `dffb10bb32a17de1b47e7dc4221444abe92cca6cca8c67a8f0fb2d8f187d8823` |
| Mission 1 current T236 timing-detail receipt | `artifacts/current_goal_t236_timing_detail_30f_20260618/labs_target_bench.json` | `2bc9eb0e4c0541a28e42b9b698c0d9f7c33b309ff58cb2c126b6c21f0cdc56f2` |
| Mission 1 rejected T236 scheduler pinning probe | `artifacts/current_goal_t236_pin_probe_20260618/summary.json` | `0a5d84b06b91188c8598407b19b0609869a019da99f7dc85ad8bb1051b53ed83` |
| Mission 1 rejected T236 scatter async-copy summary | `artifacts/current_goal_t236_scatter_async_probe_20260618/summary.json` | `5e70b1313a7c9100801d236cc2c21b4d4fae36038ce4fa225814dd39999da247` |
| Mission 1 T236 scatter async-copy baseline receipt | `artifacts/current_goal_t236_scatter_async_probe_20260618/baseline/labs_target_bench.json` | `44d041a0fad7d3a54d1321270cef874feee7baba23ed99254d39935470a55719` |
| Mission 1 rejected T236 scatter async-copy receipt | `artifacts/current_goal_t236_scatter_async_probe_20260618/async_copy/labs_target_bench.json` | `8c11dfb18616f4d268eb73500ec95378725e768fc983952bdf10fcc684d51e63` |
| Mission 1 T236 LL-Rice short sweep summary | `artifacts/current_goal_t236_llrice_sweep_GP017602_30f_20260618/summary.json` | `b3a75eacce056bcff2682f3c658ea86223cdc97b57853803ed51d1bf84e73d90` |
| Mission 1 rejected T236 LL-Rice k6556 A/B summary | `artifacts/current_goal_t236_llrice_k6556_ab_GP017602_120f_20260618/summary.json` | `0281a2bb2498dbfe56673ac7e5d4f66a73c8aa3c6873d0db8a6721bdb6f338a3` |
| Mission 1 rejected native12 chroma-unpack specialization receipt | `artifacts/mission1_chroma_specialized_t234_GP017602_120f_24fps_20260618/labs_target_bench.json` | `df7d0cec31e8e4cc098d6fd36f75152d384f2737dea5808fe69da74b8cab12ec` |
| Mission 1 rejected native12 persistent scratch receipt | `artifacts/mission1_persistent_scratch_lh3_k6656_GP017602_120f_24fps_20260618/labs_target_bench.json` | `bf8e7d5350d3dbdfed511b89b8afcd5eab377ff0b8ba57c22b530eaeed0d6ea7` |
| Mission 1 rejected native12 active-chroma scratch receipt | `artifacts/mission1_unpack_xscratch_lh3_k6656_GP017602_60f_24fps_20260618/labs_target_bench.json` | `e25b5a9ae2a288c134358641454341cc71a79b919741b5a822b0a7cb761437e3` |
| Mission 1 rejected inline jANS frequency-saturation summary | `artifacts/current_goal_jans_freq_saturate_probe_20260618/summary.json` | `926a85374ed8ee02b30b99d9db69bf8d0917f10fee046e47ea13229da451d0af` |
| Mission 1 rejected inline jANS frequency-saturation Pi receipt | `artifacts/current_goal_jans_freq_saturate_GP017602_60f_20260618/labs_target_bench.json` | `c2ad2cbd99b50db569bf80748e30bc1d4ea49149a5d40b01de218f1c70ef1da5` |
| Mission 1 rejected repo-source inline jANS frequency-saturation summary | `artifacts/current_goal_freq_saturate_repo_source_probe_20260618/summary.json` | `72e753d698875dcd30553b1e09e500b48087a8e4cbd319427b4eddb936463a2c` |
| Mission 1 rejected repo-source inline jANS frequency-saturation Pi receipt | `artifacts/current_goal_freq_saturate_repo_source_t236_GP017602_60f_20260618/labs_target_bench.json` | `c82725f60adc1d0aa4748389ac2efd749abc2906cf8ab3f471d6af27bbdfd209` |
| Mission 1 rejected T244 strict-24 Pi receipt | `artifacts/mission1_t244_GP017602_120f_24fps_20260618/labs_target_bench.json` | `80b473670783d2b62935880c017d3614558f0c4c9e54d44e43b829a34703d69c` |
| Mission 1 rejected T244 quality dashboard summary | `artifacts/mission1_native12_t244_quality_dashboard_20260618/summary.json` | `a6de24c231477907659eaa94a07e4f88d65adaa442c81f06c26e15c7fba98729` |
| Mission 1 T236 Pi build-variant no-write probe | `artifacts/current_goal_t236_build_variant_probe_GP017602_120f_20260618/summary.json` | `dc22b152fd1640652f13b11ae028afcd4d38ff63a16ad84527a2bf357b0a244a` |
| Mission 1 T236 Pi real-write build probe | `artifacts/current_goal_t236_write_build_probe_GP017602_240f_20260618/summary.json` | `d755a3c75e5c54504ce27479567a17ba8fb81186583affa99e0f5a506829d2a6` |
| Mission 1 T236 Pi write-mode probe | `artifacts/current_goal_t236_write_mode_probe_GP017602_240f_20260618/summary.json` | `ba23ea6e2891047454adb5210411cbebf5fc16d85f6d854c82759d9261c5e587` |
| Mission 1 T236 Pi write isolation probe | `artifacts/current_goal_t236_write_probe_GP017602_240f_20260618/summary.json` | `42f7ccd3a802fec255243d829884a6d5e47ab63bf2d43442863c6c0e573e1753` |
| Mission 1 clean T236 Pi no-write/write/pingpong probe | `artifacts/current_goal_t236_clean_pi_probe_GP017602_60f_20260618/summary.json` | `ab9f3b6907a56eb8a3d08a79ff0a8f419eeb9102062fa236b0a80051f40dcde0` |
| Mission 1 rejected T236 preallocated `.gvid` probe | `artifacts/current_goal_t236_prealloc_probe_GP017602_60f_20260618/summary.json` | `c3516da7cad5a716050e33af0b4566c4329197c6e72345e60a02e7da7f29cc44` |
| Mission 1 T236 SSD-read to SD-write probe | `artifacts/current_goal_t236_sdwrite_probe_GP017602_60f_20260618/summary.json` | `85111637f6694eab74b272cdd25130e27d6cd6fd5a698e26baabc1717b56eb67` |
| Mission 1 rejected T236 LTO build probe | `artifacts/current_goal_t236_lto_probe_GP017602_60f_20260618/summary.json` | `10fdb8b03128318ea637778d51788969737f41099e7f3ed3d99cbf7d02735fe2` |
| Mission 1 rejected T236 coalesce/writev scout | `artifacts/current_goal_t236_coalesce_scout_20260619/summary.json` | `55a77cd1121fbc80c2b265c47e1419585be6ff6c6697bfe3211bbde744e8b3b2` |
| Mission 1 T236 encode/write A/B/A/B partition diagnostic | `artifacts/current_goal_t236_partition_abab_probe_20260619/summary.json` | `43ffe48abe18b7e2d4508347bd1fd2241d66b7cd85f5cdab90c6fa709990a848` |
| Mission 1 native12 write-contention summary | `artifacts/mission1_write_contention_summary_20260618/summary.json` | `e91e92ca8850b27bea4d407f9bc6ce736def71fc374faca0794a9f28e3047a06` |
| Mission 1 native12 strict-24 gap report | `artifacts/current_goal_mission1_strict24_gap_report_20260619/summary.json` | `62ed4df38d33b76729618cf767f096c22475a61871934c35b1220fc1acb4cd8d` |
| Mission 1 strict-24 probe-matrix summary | `artifacts/current_goal_strict24_probe_matrix_20260619/summary.json` | `ee44022cf6e20654d4e182a0de03a4d89115a932215e0b88f168a9f2d86ea4f0` |
| Mission 1 strict-24 current-source repeat receipt | `artifacts/current_goal_strict24_probe_matrix_20260619/current_source_sustained_repeat_240f/labs_target_bench.json` | `1d9a0789280e720c69fe4fc54206eaa4d88005ed517f155dc5d171573ea26fc5` |
| Mission 1 strict-24 instrumented hot-row profile receipt | `artifacts/current_goal_strict24_probe_matrix_20260619/encoder_hotrow_profile_30f/labs_target_bench.json` | `8e26b9d783bbd59df6cda4e22de05e9daf59bb06a910a7453fb5145b26bc0735` |
| Mission 1 strict-24 production-profile best repeat receipt | `artifacts/current_goal_strict24_probe_matrix_20260619/legacy_policy_ab_240f/labs_target_bench.json` | `573494da30028870ebdabdab4b8889b582ba445b1186d48bfa4c21116bbcca0e` |
| Mission 1 strict-24 production-profile jitter repeat receipt | `artifacts/current_goal_strict24_probe_matrix_20260619/production_profile_240f/labs_target_bench.json` | `d3c7e571f82fa157c7419969affcbdbdf9e22aee799d66eb4f44e36fdf7e1d8e` |
| Mission 1 strict-24 production-profile settled repeat receipt | `artifacts/current_goal_strict24_probe_matrix_20260619/production_profile_repeat2_240f/labs_target_bench.json` | `d2a6522b598a7f55fefed56d46136b0177b447a185371e16eebcf7d6ffdb5e58` |
| Mission 1 strict-24 production-profile labeled hot-row receipt | `artifacts/current_goal_strict24_probe_matrix_20260619/production_profile_labeled_hotrow_30f/labs_target_bench.json` | `2062d837e20b6c6993a7180a8a4c02e1bbefee0b5f253da3e7fa5e960cf40017` |
| Mission 1 rejected T233 ch0/ch3 LH+HL threshold timing receipt | `artifacts/current_goal_strict24_probe_matrix_20260619/production_profile_ch03_lhhl_plus1_120f/labs_target_bench.json` | `b569efb475e96dec880c591c332d4c184f000a82fa5b8fdd79694c0810a843a4` |
| Mission 1 rejected T233 ch0/ch3 LH+HL threshold quality dashboard | `artifacts/mission1_native12_t233_ch03_lhhl_plus1_quality_dashboard_20260619/summary.json` | `aced19ac49001a3bf8e783e163a9de9c16ff14c9a258d144975e7f683f10dd38` |
| Mission 1 rejected T233 ch0/ch3 LH threshold timing receipt | `artifacts/current_goal_strict24_probe_matrix_20260619/production_profile_ch03_lh_plus1_120f/labs_target_bench.json` | `54948ba508009f79e450fd2b58fc0fb5ea07e3857e0c31fbe924db86e2fde905` |
| Mission 1 rejected T233 ch0/ch3 LH threshold quality dashboard | `artifacts/mission1_native12_t233_ch03_lh_plus1_quality_dashboard_20260619/summary.json` | `50db6a4119ed3a358dc4cb0560875161746b41f9b52fbafcf59158c204b6d055` |
| Mission 1 rejected T233 ch0/ch3 HL threshold timing receipt | `artifacts/current_goal_strict24_probe_matrix_20260619/production_profile_ch03_hl_plus1_120f/labs_target_bench.json` | `c50943ccc5f55c959a0cc9a44a3cfd413c3211c57143e4ec4f21eaf4f27a43dd` |
| Mission 1 rejected T233 ch0/ch3 HL threshold quality dashboard | `artifacts/mission1_native12_t233_ch03_hl_plus1_quality_dashboard_20260619/summary.json` | `4d43f3ba440ddcb0b3a7481c8f0631a1ba9f0c0381fd2dc6be7567e3ee3cdf98` |
| Mission 1 rejected T233 ch0-only LH threshold quality dashboard | `artifacts/mission1_native12_t233_ch0_lh_plus1_quality_dashboard_20260619/summary.json` | `f83b7ff37e0d6fdc05b5ab4214af224c2b2e886e78feadf0c759cb1f3755506a` |
| Mission 1 rejected T233 ch3-only LH threshold quality dashboard | `artifacts/mission1_native12_t233_ch3_lh_plus1_quality_dashboard_20260619/summary.json` | `ac28b32696ba93c8dfda497fc0f056cbf2a28e8b14b643fdb1deac46e16f4f44` |
| Mission 1 rejected T236 exact-PGO layout probe | `artifacts/current_sync_t236_exact_encode_pgo_ofast_20260618/summary.json` | `abdf14c61fd609849a008ddd1c84105c25ea1d89d047fd94da4cea7acc68e787` |
| Mission 1 current T236 jANS row assembly excerpt | `artifacts/current_goal_t236_jans_asm_review_20260618/jans_inline_row_current_objdump.txt` | `493eb16944db5faa087115cce611adbdfa37fcdffc44fcbd4d3825b48721471b` |
| Mission 1 current T236 jANS symbol receipt | `artifacts/current_goal_t236_jans_asm_review_20260618/nm_jans_symbols_current.txt` | `fc45e19201e9804066c0ba217c0f44aaa157bb8c08b5d1f03860733849a53a50` |
| Mission 1 rejected T236 layout/alignment flags probe | `artifacts/current_goal_t236_layoutalign_probe_GP017602_120f_20260618/summary.json` | `30d0842e5b56aef4836b43bcf0e5b7bfc255b74ccf45aae4445daa2b7b4c1bcb` |
| Mission 1 rejected T236 process I/O priority probe | `artifacts/current_sync_t236_ionice_probe_20260618/summary.json` | `4d5ddf469a6bc36db4a510f2e1a6b94406a15eb7d9ddabf8118edeb48f955b38` |
| Mission 1 T236 sync-range baseline receipt | `artifacts/current_goal_t236_syncrange_probe_GP017602_120f_20260618/baseline/labs_target_bench.json` | `f8f8d98173f30ceeb05825e44c7c83670d0f0a65409710d572edd0102679c7f9` |
| Mission 1 rejected T236 sync-range receipt | `artifacts/current_goal_t236_syncrange_probe_GP017602_120f_20260618/sync_range/labs_target_bench.json` | `378aa1db5e87b5ef76bfc7114133008a5221f50976cc7a1ef3f63efb465c67e4` |
| Mission 1 rejected live T236 sync-range refresh | `artifacts/current_goal_live_t236_exact_sync_range_ab_GP017602_60f_20260619/summary.json` | `70b6fbe21c282a1f3c705faa55389f5b40cd18d750befe9b22739a2d4d85a9f6` |
| Mission 1 live T236 exact-profile baseline refresh | `artifacts/current_goal_live_t236_exact_sync_range_ab_GP017602_60f_20260619/baseline/labs_target_bench.json` | `68b46fd54d083da9720930b6af38b08e5a6c1704cd697134b55831b4e01422c5` |
| Mission 1 rejected T236 NEON zero-scan receipt | `artifacts/current_goal_t236_neonzero_GP017602_120f_20260618/labs_target_bench.json` | `e8ff34d9305ca12030e4cab490f0f95bfb20dfdfe98d46c493749232632c1f0e` |
| Mission 1 rejected T236 explicit-offset pwritev receipt | `artifacts/current_goal_t236_pwritev_probe_GP017602_120f_20260618/labs_target_bench.json` | `9832a1e5a09ef23f93107b6fe757b7069d6d1658e6c2da5ba8f83fcb48261f8e` |
| Mission 1 rejected T236 coalesced-header probe | `artifacts/current_goal_t236_coalesce_probe_GP017602_240f_20260618/summary.json` | `b95a7c63bc9def76dc5a72dab7fe6457ba051d5962289e2b74a931ca3e8742a7` |
| Mission 1 rejected T236 coalesced-header native-build probe | `artifacts/current_goal_t236_coalesce_native_probe_GP017602_240f_20260618/summary.json` | `32ea60327fca0148936a09b91699c5a03f2be9d83129b62bf5df7f8fcddadaf9` |
| Mission 1 T236 indexed-writev near-miss probe | `artifacts/current_goal_writev_index_probe_GP017602_240f_ba_20260618/summary.json` | `6f756dfe60cd48f3bafbdc4858f59fe5f44faac3ac242248ea28e3007f2e548e` |
| Mission 1 T236 coalesced-prefix plus indexed-writev near-miss probe | `artifacts/current_goal_t236_coalesce_index_probe_GP017602_240f_ab_20260618/summary.json` | `779dbdb492e5f7ccf2fd689672dfed89e81609bed6d53625cad3c3c01bb32134` |
| Mission 1 rejected current-source coalesced-prefix probe | `artifacts/current_goal_coalesce_prefix_source_probe_GP017602_120f_summary_20260618/summary.json` | `9bde02e37928a0dbf3983d8c648f8cb88de1948be90193340298aed48845b603` |
| Mission 1 rejected jANS zero-scan32 probe | `artifacts/current_goal_jans_zero_scan32_probe_GP017602_summary_20260618/summary.json` | `1a1142dde348c81112eeb370f07ba6cefd5e5e6a1c072da1f675c2e5ebf12920` |
| Mission 1 rejected T236 GVID frame-prefix coalescing probe | `artifacts/current_goal_t236_frameprefix_probe_GP017602_120f_ab_20260618/summary.json` | `4de216d7c45024be13540425c844572a19739daaeecc60d9fff8fd2f1da0559e` |
| Mission 1 rejected T236 current-source Ofast probe | `artifacts/current_goal_t236_ofast_coalesce_probe_GP017602_120f_ab_20260618/summary.json` | `e9d3c6793e3f875574ffb355e714beb80989a709c540d2ff8b1cbc8282a960e5` |
| Mission 1 rejected T236 DONTNEED summary | `artifacts/current_goal_t236_dontneed_probe_GP017602_240f_20260618/summary.json` | `759febbd011f2f32d46b13ad32e2b86de0f5655b3d4992ddcdb10a9a043ddcca` |
| Mission 1 rejected T236 DONTNEED baseline receipt | `artifacts/current_goal_t236_dontneed_probe_GP017602_240f_20260618/baseline/labs_target_bench.json` | `fe6a8a89b3ee8f75613c45b9566c3b563fa063f85fba9c81a97283b755c97bce` |
| Mission 1 rejected T236 DONTNEED candidate receipt | `artifacts/current_goal_t236_dontneed_probe_GP017602_240f_20260618/dontneed/labs_target_bench.json` | `59a058b731274389619701af8903ec7e09f7d57412e5b6b1e2c11c9c5f7130ca` |
| Mission 1 T236 post-audit stale-target-source Pi receipt | `artifacts/current_goal_postaudit_t236_GP017602_60f_20260618/labs_target_bench.json` | `af6ab99c3bdadb7e407cde4648ad86fe59fa8f68f83fca1913c92471f897eec7` |
| Mission 1 T236 current repo-source Pi receipt | `artifacts/current_goal_repo_source_t236_GP017602_60f_20260618/labs_target_bench.json` | `d1732fdc56b6791f823f1600dd7a85922733f045d3010aad58eb90b0d95b6927` |
| Mission 1 T236 current source-provenance sustained Pi receipt | `artifacts/current_goal_provenance_t236_GP017602_240f_20260618/labs_target_bench.json` | `83e062209133a2e3f0c3f3dcd949e47681ff2da72c29c78f8d9080637017ad5a` |
| Mission 1 T236 explicit loop/wall gap Pi receipt | `artifacts/current_goal_gap_receipt_t236_GP017602_240f_20260618/labs_target_bench.json` | `1046e264e674409aebe5579e219da91590955a78a94714af67f2c9828133cb9b` |
| Mission 1 rejected T236 fused hard-threshold tokenizer probe | `artifacts/current_goal_jans_fused_hardt_probe_GP017602_summary_20260618/summary.json` | `08ca56972ea7dec91853397b2e951d1bc881469917aa45dd97af43cb73ce2b74` |
| Mission 1 T236 cleaned-source post-rejection Pi receipt | `artifacts/current_goal_clean_baseline_GP017602_240f_after_fused_hardt_reject_20260618/labs_target_bench.json` | `ceaa3b5116a3d4c6ede5be8d02abdcd19b367a1305115039979b32fba2821b42` |
| Mission 1 accepted T236 inline frequency-saturation summary | `artifacts/current_goal_inline_freq_saturate_t236_GP017602_summary_20260618/summary.json` | `fdf68489b56703a628158f1f97241ef7476792e2709a9fb02011a2d51cbdda2d` |
| Mission 1 accepted T236 inline frequency-saturation 120-frame receipt | `artifacts/current_goal_inline_freq_saturate_t236_GP017602_summary_20260618/120f/labs_target_bench.json` | `fe135d7ed914be0fa9bddd53618789e70c14289cec3ecf2593ff00a953f8ed1b` |
| Mission 1 accepted T236 inline frequency-saturation 240-frame receipt | `artifacts/current_goal_inline_freq_saturate_t236_GP017602_summary_20260618/240f/labs_target_bench.json` | `e19e4cdcb50297ddd19882a72caa3d41604f4c2f665185f8faaca30cf3dc2bf8` |
| Mission 1 rejected T236 post-saturation stripe sweep summary | `artifacts/current_goal_inline_freq_saturate_stripe_sweep_GP017602_120f_20260618/summary.json` | `048002a3a3b389c7999e158996273a505209d1f853753511d4a9d7b78a0664dd` |
| Mission 1 rejected T236 post-saturation stripe256 receipt | `artifacts/current_goal_inline_freq_saturate_stripe_sweep_GP017602_120f_20260618/stripe256/labs_target_bench.json` | `ad127f15234b52c4f12d630bfc3ddc70d64d93bfe488e13ea422d4a4b9ba8d7b` |
| Mission 1 rejected T236 post-saturation stripe264 receipt | `artifacts/current_goal_inline_freq_saturate_stripe_sweep_GP017602_120f_20260618/stripe264/labs_target_bench.json` | `6ff315bac2a3217c910f12179bf278fccfcf219814f8eb103c5b0f17b1352832` |
| Mission 1 rejected T236 post-saturation stripe320 receipt | `artifacts/current_goal_inline_freq_saturate_stripe_sweep_GP017602_120f_20260618/stripe320/labs_target_bench.json` | `e09c36f15e4054ed11302925b58ba7c426dce4b198fa2f21df7fc77146020714` |
| Mission 1 rejected T236 post-saturation stripe384 receipt | `artifacts/current_goal_inline_freq_saturate_stripe_sweep_GP017602_120f_20260618/stripe384/labs_target_bench.json` | `23846f9a08973e0e61b467a709b77ec57076a3074c7aacfba8eab0a35f5511ef` |
| Mission 1 accepted LL bitwriter32 timing summary | `artifacts/current_goal_ll_bitwriter32_probe_GP017602_20260618/summary.json` | `2429266ab390b98f6355c6240c32a0379a92d6dcadb9cecf65b35fc0ab2b560e` |
| Mission 1 LL bitwriter32 accepted-baseline 240-frame receipt | `artifacts/current_goal_ll_bitwriter32_probe_GP017602_20260618/baseline_240f/labs_target_bench.json` | `e8458ac0334fc74e94eb22137fabb7db4e02952ed3b61496d9443e44d80cc092` |
| Mission 1 LL bitwriter32 candidate 240-frame receipt | `artifacts/current_goal_ll_bitwriter32_probe_GP017602_20260618/candidate_240f/labs_target_bench.json` | `138ee9952604772d3a8bb8a42e2d7025f81337a8e206c828d0faee1271483b65` |
| Mission 1 rejected LL bitwriter32 pinning summary | `artifacts/current_goal_ll_bitwriter32_pin_probe_GP017602_20260618/summary.json` | `a27a0bfbfc60c1effc2d4762175fa3efc45d55705617735eff3ac2e6d084bf46` |
| Mission 1 rejected LL bitwriter32 pinned receipt | `artifacts/current_goal_ll_bitwriter32_pin_probe_GP017602_20260618/pinned_120f/labs_target_bench.json` | `19d8fabd2d5edf1a657edfa61a407f05f1dc4d21fa8cea442816a6d2ef29e9b1` |
| Mission 1 LL bitwriter32 no-pin repeat receipt | `artifacts/current_goal_ll_bitwriter32_pin_probe_GP017602_20260618/nopin2_120f/labs_target_bench.json` | `94d4330085f3a74381580bfd5ce81b77622d81d9e8ddc34b435f7d9930b415ff` |
| Mission 1 LL bitwriter32 timing-detail refresh receipt | `artifacts/current_goal_ll_bitwriter32_timing_detail_GP017602_30f_20260618/labs_target_bench.json` | `99c3a9a897ad4d2e109c5118b429baa721e96e7b121a8cee7776c25570d3e26c` |
| Mission 1 rejected `-Ofast` PGO/code-layout probe summary | `artifacts/current_goal_pgo_ofast_probe_GP017602_20260618/summary.json` | `7405f254696769d6f1abcbaac645a37a3d6a786b282f16541cd6a096a0552c95` |
| Mission 1 rejected rANS reverse-write and PGO/code-layout repeat summary | `artifacts/current_goal_encode_rejection_summary_20260619/summary.json` | `50ec5f256bd45f9d7bea85d684db2c9d8f2b981f56c9ff85d31de0a7a9f2155a` |
| Mission 1 rejected rANS reverse-write 120-frame receipt | `artifacts/current_goal_jans_revwrite_ofast_probe_GP017602_120f_20260619/labs_target_bench.json` | `4a74697a990559f4b4f1bf63883c48fa0219d2ac736ee3b393135fca01904cf9` |
| Mission 1 rejected PGO/code-layout 120-frame receipt | `artifacts/current_goal_pgo_probe_GP017602_120f_20260619/labs_target_bench.json` | `c0316a96f4ae31b40b069a2d74bb6a7164fb4b6f586cca39fc219b8410c02bfd` |
| Mission 1 same-session baseline repeat for rejected encode probes | `artifacts/current_goal_baseline_repeat_GP017602_120f_20260619/labs_target_bench.json` | `5bafbe36a948f6d182b668b8e103a3f286d8054866c3eda9bf628532862657fe` |
| Mission 1 rejected jANS NEON lane-extract probe summary | `artifacts/current_goal_jans_lane_extract_probe_GP017602_20260618/summary.json` | `adc1918d3669fbcaa4b79fe3ca5e81d7802f69cc100457e0d250b739168f1958` |
| Mission 1 accepted-baseline receipt for lane-extract A/B | `artifacts/current_goal_jans_lane_extract_probe_GP017602_20260618/baseline_120f/labs_target_bench.json` | `408c6925abda3b3f2971db733e0b355fbe877f2d836fdb2afeebf19e3c285cc1` |
| Mission 1 rejected lane-extract candidate receipt | `artifacts/current_goal_jans_lane_extract_probe_GP017602_20260618/candidate_120f/labs_target_bench.json` | `bb5ae731ac06d4ea230d00c1fa9d4e63f3a0c2180b1789174ee4f422c3e78168` |
| Mission 1 rejected lane-extract candidate repeat receipt | `artifacts/current_goal_jans_lane_extract_probe_GP017602_20260618/candidate2_120f/labs_target_bench.json` | `b16325545525eb38ab40005e1a5c9f451065c8efe5cd8e9a814ffdf3cd17141b` |
| Mission 1 rejected T236 inline 32-bit frequency side-table probe | `artifacts/current_goal_inline_freq32_t236_GP017602_summary_20260618/summary.json` | `cc0a3528671af81ddd7010cd21bce063d1ad3243b287d804ae2ecbea494aff49` |
| Mission 1 rejected T236 inline 32-bit frequency side-table receipt | `artifacts/current_goal_inline_freq32_t236_GP017602_summary_20260618/120f/labs_target_bench.json` | `3877b6f9d4535dc1887b4e151b50c46e6a64ae1ef14d1e1a1e7f58405d8ad6bc` |
| Mission 1 rejected detail-restored-low SR delta summary | `artifacts/current_goal_sr_detail_restored_hardrows_eval_20260619/delta_summary.json` | `00c46b47daab3952b93506fb01b4e31f897b58bcd0eaa97d589cab5ea19c7ca6` |
| Mission 1 detail-restored-low diagnostic receipt | `artifacts/current_goal_sr_detail_restored_hardrows_eval_20260619/detail_lows_receipt.json` | `a4e8932672912828b2e01b603f7015529e91231cd17572d7c8b548d7577607d5` |
| Mission 1 detail-restored-low SR hard-row dashboard summary | `artifacts/current_goal_sr_detail_restored_hardrows_eval_20260619/sr_eval/summary.json` | `47a990339b6c9f9f19d47499ae679125323ff99cfb2b59dd12900433e046173e` |
| Mission 1 retargeted detail-restored hard4 SR pair set | `artifacts/current_goal_sr_detail_retarget_pairs_20260619/mission_all42_t233_detail_restored_hard4_inputs_w96.npz` | `0a8372b319ca2c68546cea734de6148ff4d2c6cd87b3b7434f06c9a767cd80ca` |
| Mission 1 retargeted detail-restored hard4 SR pair sidecar | `artifacts/current_goal_sr_detail_retarget_pairs_20260619/mission_all42_t233_detail_restored_hard4_inputs_w96.npz.json` | `77234f44fe32fa65fc7a48429a585bf0a6ee8e6ffd1244b43aa1d1b4cfa06464` |
| Mission 1 rejected detail-retarget fine-tune decision | `artifacts/current_goal_sr_detail_retarget_finetune_20260619/decision.json` | `7a824a08883883e439f2952db745fa96a65878d2d848e191487cacf555168795` |
| Mission 1 rejected detail-retarget fine-tune checkpoint | `artifacts/current_goal_sr_detail_retarget_finetune_20260619/detail_retarget_hard4_from_registered_w48_d6_rs03_400.pt` | `5415521809d100b6860e535a49b2d066a446c383325dcabfa54876a17a41b6fc` |
| Mission 1 rejected detail-retarget fine-tune training receipt | `artifacts/current_goal_sr_detail_retarget_finetune_20260619/detail_retarget_hard4_from_registered_w48_d6_rs03_400.pt.json` | `acdb1b7ecc34df0ece41d6a950b27ff43ed5295bee20b7ceaba40c4a13208b4d` |
| Mission 1 detail-retarget step-200 full-frame summary | `artifacts/current_goal_sr_detail_retarget_finetune_20260619/mission_detail_lows_step0200_fullframe/summary.json` | `9b91e1a0791dbf57c68a7c14d698d460b8e5a2727ac190a817281c70e4f780c2` |
| Mission 1 detail-retarget step-400 full-frame summary | `artifacts/current_goal_sr_detail_retarget_finetune_20260619/mission_detail_lows_step0400_fullframe/summary.json` | `5cf29ee4c370bda3e66061bfb92e16f269ec46aba8ab0b857e04a3c143943915` |
| Mission+Z8 detail-retarget mixed SR pair set | `artifacts/current_goal_sr_detail_retarget_mixed_pairs_20260619/mission42_z8_t233_detail_restored_hard4_inputs_w96.npz` | `d15894fe553ab90898d1c3a53acd60c1696e3fb83cea51a406890ff70b2000d5` |
| Mission+Z8 detail-retarget mixed SR pair sidecar | `artifacts/current_goal_sr_detail_retarget_mixed_pairs_20260619/mission42_z8_t233_detail_restored_hard4_inputs_w96.npz.json` | `b910de88b506b9ba34f9d38eef6f694064dcde6f0d8536c7dcf617d733d588b1` |
| Mission+Z8 rejected detail-retarget mixed checkpoint | `artifacts/current_goal_sr_detail_retarget_mixed_finetune_20260619/detail_retarget_mixed_from_registered_w48_d6_rs03_1600.pt` | `a5c26ca5447e3cb2cd1b3880ddc64f9e56e5573af8de06e31eec088981a4f3b5` |
| Mission+Z8 rejected detail-retarget mixed training receipt | `artifacts/current_goal_sr_detail_retarget_mixed_finetune_20260619/detail_retarget_mixed_from_registered_w48_d6_rs03_1600.pt.json` | `e9771f1d9f3fc51353a2a221b72a52e84335ead8c65962b634cc41b1b5b98054` |
| Mission+Z8 rejected detail-retarget mixed decision | `artifacts/current_goal_sr_detail_retarget_mixed_finetune_20260619/detail_retarget_mixed_decision.json` | `4aa2331123d1759e415fe5e1a76b6c580b78e6c53780852b4ddc80e68636b863` |
| Mission detail-restored hard rows, mixed step-1200 summary | `artifacts/current_goal_sr_detail_retarget_mixed_finetune_20260619/mission_detail_lows_step1200_fullframe/summary.json` | `b047501859928b7a99d8acd3e985ffaddfd2d8cf3c3d1141babeafb8ef5d4954` |
| Mission normal current lows, mixed step-1200 summary | `artifacts/current_goal_sr_detail_retarget_mixed_finetune_20260619/mission_current_lows_step1200_fullframe/summary.json` | `284e010d05c788d6e7403ec8beca37938a59e12a02fd9ad6bc45f601ea741321` |
| Z8 holdout, mixed step-1200 summary | `artifacts/current_goal_sr_detail_retarget_mixed_finetune_20260619/z8_holdout5_step1200_fullframe/summary.json` | `d46c7ceb7343b3798f60dc2d04633e78eee5bf7f08065c17bd1d43fe6bdd11b9` |
| Mission detail-sidecar specialist checkpoint | `artifacts/current_goal_sr_detail_sidecar_specialist_20260619/detail_sidecar_specialist_from_mixed_step1200_w48_d6_rs03_800.pt` | `1ff0837abef270673f5752b591740275bd0ab2cb15f6693da5e703b590ef3df6` |
| Mission detail-sidecar specialist training receipt | `artifacts/current_goal_sr_detail_sidecar_specialist_20260619/detail_sidecar_specialist_from_mixed_step1200_w48_d6_rs03_800.pt.json` | `85550fa495ccb4c1c4ca17d8e462e1093a5c5e99afcdff274e9cfb7d770d65db` |
| Mission detail-sidecar specialist step-600 summary | `artifacts/current_goal_sr_detail_sidecar_specialist_20260619/mission_detail_lows_step0600_fullframe/summary.json` | `f5884f62acdef2e0a560095a12fa9bff4721e3cc2696e6cb4b03411f240e4add` |
| Mission detail-sidecar specialist continuation checkpoint | `artifacts/current_goal_sr_detail_sidecar_specialist_continue_20260619/detail_sidecar_specialist_from_step600_w48_d6_rs03_600.pt` | `56cd2181ba33d7e0b4e577f725c8d26838882723aa9fc404617c268a95cd13b1` |
| Mission detail-sidecar specialist continuation training receipt | `artifacts/current_goal_sr_detail_sidecar_specialist_continue_20260619/detail_sidecar_specialist_from_step600_w48_d6_rs03_600.pt.json` | `200c5b70005aad3106058c5c8768b78957a468398766c76a04b365c64ac23503` |
| Mission detail-sidecar specialist continuation step-600 summary | `artifacts/current_goal_sr_detail_sidecar_specialist_continue_20260619/mission_detail_lows_step0600_fullframe/summary.json` | `caa4703cb3b7b411f1c2acf68da5f99f49ecf19cbe9f67908e5e4b52a7965b97` |
| Mission rejected detail-sidecar specialist decision | `artifacts/current_goal_sr_detail_sidecar_specialist_20260619/detail_sidecar_specialist_decision.json` | `aaf91cf551e77a7340e030e0bd779e18681e7921555f8a211732a1b2d0e064ef` |
| Mission rejected detail-sidecar adapter decision | `artifacts/current_goal_sr_detail_sidecar_adapter_from_specialist_20260619/detail_sidecar_adapter_decision.json` | `f246edc36240c051b5ce6330cbb01ebe2169f4160d0bc4869ca06e8d1281b53c` |
| Mission detail-sidecar hard-tile manifest GP017349/GP017604 | `artifacts/current_goal_sr_detail_sidecar_hardtile_adapter_20260619/gp017349_gp017604_detail_sidecar_hardtiles_w96_s32_top160.json` | `ca481ec5f01fb234e635d0f27280945841c7cff631a276db59b271bd0b9cff61` |
| Mission detail-sidecar hard-tile retargeted pair set | `artifacts/current_goal_sr_detail_sidecar_hardtile_adapter_20260619/gp017349_gp017604_hardtiles_detail_lows_w96.npz` | `645f083a18763a93cd0b82469ff5ecdf783b51ebaae29b54c0bd18fb61af6960` |
| Mission detail-sidecar hard-tile adapter checkpoint | `artifacts/current_goal_sr_detail_sidecar_hardtile_adapter_20260619/hardtile_adapter_from_specialist_step600_w48_d6_rs03_1200.pt` | `ddc10f03144c670fdaf76bfaeb02a0fb677320110eb44eaebedfb05a4a12ad6c` |
| Mission detail-sidecar hard-tile adapter training receipt | `artifacts/current_goal_sr_detail_sidecar_hardtile_adapter_20260619/hardtile_adapter_from_specialist_step600_w48_d6_rs03_1200.pt.json` | `aa749639468006b4627e1db24747aa3da9985e6725b11a2797ca275e9d9c5b98` |
| Mission detail-sidecar hard-tile adapter step-1200 summary | `artifacts/current_goal_sr_detail_sidecar_hardtile_adapter_20260619/mission_detail_lows_step1200_fullframe/summary.json` | `09d8efb1330f9fc3979d983a73e1d96cf530bf1078d5c6de42215c09fbaeada7` |
| Mission rejected detail-sidecar hard-tile adapter decision | `artifacts/current_goal_sr_detail_sidecar_hardtile_adapter_20260619/hardtile_adapter_decision.json` | `b85af8801cee8f1e7029933c60a263f703b70c9a022c5f91b8d75928a6fbe4e0` |
| Mission GP017349 SR error decomposition summary | `artifacts/current_goal_sr_gp017349_error_decomposition_20260619/gp017349_error_decomposition_summary.json` | `3c90eac4b023b3d83623be7b59641b46cb9632c348746625988057164c7ecea2` |
| Mission GP017349 registered SR decomposition | `artifacts/current_goal_sr_gp017349_error_decomposition_20260619/registered_gp017349_decomposition.json` | `a761f366eb3d3ec5029f8544cc29bec9d4916ba979afbbed22d36ddcbff076cf` |
| Mission GP017349 sidecar-specialist SR decomposition | `artifacts/current_goal_sr_gp017349_error_decomposition_20260619/sidecar_specialist_gp017349_decomposition.json` | `ba03597d36596608564b37b785d4a669bf8b2f407eba457f6be7572cfe507042` |
| Mission GP017349 hard-tile-adapter SR decomposition | `artifacts/current_goal_sr_gp017349_error_decomposition_20260619/hardtile_adapter_gp017349_decomposition.json` | `13ef8e20338f9e6713a65891ad0aa32f0c8429c96122707dbe90f654047ebd00` |
| Mission rejected GP017349 green-plane adapter checkpoint | `artifacts/current_goal_sr_gp017349_green_plane_adapter_20260619/green_plane_hardtile_adapter_from_specialist_w48_d6_rs03_1200.pt` | `895ddffbe15c8ede38dee8a1ba60fa07eafc776b88c8921d700a4b7625b5f746` |
| Mission rejected GP017349 green-plane adapter training receipt | `artifacts/current_goal_sr_gp017349_green_plane_adapter_20260619/green_plane_hardtile_adapter_from_specialist_w48_d6_rs03_1200.pt.json` | `f318e616ba059a8cedffdf41fe1ec1cebdba9904b067b9b05eeb09232bd879eb` |
| Mission rejected GP017349 green-plane step-1200 decomposition | `artifacts/current_goal_sr_gp017349_green_plane_adapter_20260619/green_step1200_gp017349_decomposition.json` | `96d18918aea40e8d2b92bfb807f252f2eedafbe9d9cb7c063b9407b2e5a6442d` |
| Mission GP017349 green phase oracle probe | `artifacts/current_goal_sr_gp017349_green_phase_oracle_20260619/gp017349_green_phase_oracle_probe.json` | `44d2ffa2265113a4beb95ee4dbd87de47e10bbf64ad9e5ec3d025049b4773fea` |
| Mission GP017349 green phase oracle decision | `artifacts/current_goal_sr_gp017349_green_phase_oracle_20260619/gp017349_green_phase_oracle_decision.json` | `d123de1b66c19ad4132375e0ab26df4f8800dbc1d8996e441d092d92d7c8aee7` |
| Mission GP017349 green phase oracle full-frame summary | `artifacts/current_goal_sr_gp017349_green_phase_oracle_20260619/hardtile_best_keepraw/summary.json` | `869a375ac1701f404b60751e206bfe71fe0dbe8f49d7250dc322869289dea08f` |
| Mission GP017349 green phase oracle detail-low receipt | `artifacts/current_goal_sr_gp017349_green_phase_oracle_20260619/gp017349_detail_low_receipt.json` | `bb5841aadee21bfab65161b01bf1462f1a4fd7a3517e2b10fddada793d47ad6e` |
| Mission rejected green-detail adapter checkpoint | `artifacts/current_goal_sr_green_detail_adapter_20260619/green_detail_adapter_from_hardtile_step1200_w48_d6_rs03.pt` | `a47073b72fbcb2bc4859dca2fa8f7d7a4d4c6a7d54ee1b14057e8cba5b2cdd64` |
| Mission rejected green-detail adapter training receipt | `artifacts/current_goal_sr_green_detail_adapter_20260619/green_detail_adapter_from_hardtile_step1200_w48_d6_rs03.pt.json` | `69a456c0cf82f787368087bc2bae84bde3efd5436fc7bdf4d04b0b0293d35ac3` |
| Mission rejected green-detail adapter decision | `artifacts/current_goal_sr_green_detail_adapter_20260619/green_detail_adapter_decision.json` | `753e7f269e2e285ccb6293a24415cdf8592987b07703df8b17d0be39bdbc7d7f` |
| Mission green-detail adapter step-600 full-frame summary | `artifacts/current_goal_sr_green_detail_adapter_20260619/mission_detail_lows_step000600_fullframe/summary.json` | `0f0665d3f053925e597cc799120c5b83d306ffae310f810e1bcccd25fd4c5dd9` |
| Mission green-detail adapter step-1200 full-frame summary | `artifacts/current_goal_sr_green_detail_adapter_20260619/mission_detail_lows_step001200_fullframe/summary.json` | `6d7c839c354c1e41cc29d72abeadbeac47e854dfd86d9b3eb6dc88a52949931b` |
| Mission green-detail adapter detail-low hard4 receipt | `artifacts/current_goal_sr_green_detail_adapter_20260619/detail_lows_hard4_receipt.json` | `3061bd450243b332a966317f77487588af90f5e06e763a0ed57a647ab642c63d` |
| Mission rejected broad green-detail adapter checkpoint | `artifacts/current_goal_sr_green_detail_broad_adapter_20260619/green_detail_broad_from_hardtile_w48_d6_rs03_800.pt` | `26b4f95bb1d65b165e4652ba8f92578bf539a743600ebb6aba2f9e448ab17376` |
| Mission rejected broad green-detail adapter training receipt | `artifacts/current_goal_sr_green_detail_broad_adapter_20260619/green_detail_broad_from_hardtile_w48_d6_rs03_800.pt.json` | `d493309f2578a55fcd28f2129e5bdf669707aa81e96ceb0fa970a0cf6d5adc94` |
| Mission rejected broad green-detail adapter decision | `artifacts/current_goal_sr_green_detail_broad_adapter_20260619/green_detail_broad_adapter_decision.json` | `d6ba39654c4af09d3eff2aefa2be672e15f279002a0c7b4375a6f5204bcc8a22` |
| Mission broad green-detail adapter step-800 full-frame summary | `artifacts/current_goal_sr_green_detail_broad_adapter_20260619/mission_detail_lows_step000800_fullframe/summary.json` | `4454a43d70ee105531dbef307a461d6e29dc42fbe98c74f7621c2202cd5c8f4e` |
| Mission rejected GP017349 large-context decision | `artifacts/current_goal_sr_gp017349_large_context_20260619/gp017349_large_context_decision.json` | `8f5e8fffd877981b2af3b2a6a03465a120ef4f31f0e62588dbad3ee392990bb8` |
| Mission GP017349 large-context hard-tile manifest | `artifacts/current_goal_sr_gp017349_large_context_20260619/gp017349_large_context_hardtiles_w192_s64_top96.json` | `12570c6ecb0a43b3526832f4ad85896a7b6d4baa180f018e91e78003d7e86596` |
| Mission GP017349 large-context detail-low pair set | `artifacts/current_goal_sr_gp017349_large_context_20260619/gp017349_large_context_detail_lows_w192.npz` | `a7b3d33813edcf3e3a96ecd9788c431184e50fcb6d6e6299936a342aa3cb0707` |
| Mission GP017349 large-context detail-low pair sidecar | `artifacts/current_goal_sr_gp017349_large_context_20260619/gp017349_large_context_detail_lows_w192.npz.json` | `b1161207b29637cfaa48bd563bddcd115145f21f0f8119003d5d3d5cb0f28c2f` |
| Mission rejected GP017349 large-context green-only checkpoint | `artifacts/current_goal_sr_gp017349_large_context_20260619/green_detail_large_context_gp017349_w48_d6_rs03_600.pt` | `8ee453b127da08631c6d95536f327d4d57a9784e3455b57fd90fdd5728c2d35c` |
| Mission rejected GP017349 large-context adapter+green checkpoint | `artifacts/current_goal_sr_gp017349_large_context_20260619/adapter_green_large_context_gp017349_w48_d6_rs03_600.pt` | `9188ac740b5682b7d5f9b69ffc8dec31aee6e2ff067fefd418153e5429756a42` |
| Mission rejected GP017349 large-context adapter+green continuation checkpoint | `artifacts/current_goal_sr_gp017349_large_context_20260619/adapter_green_large_context_gp017349_continue_w48_d6_rs03_1800.pt` | `c24ecb6453928cdb7a0be7abfd4533ed70c8b27d7e28a299e4a75ddf3902c5e2` |
| Mission GP017349 large-context step-1800 hard4 summary | `artifacts/current_goal_sr_gp017349_large_context_20260619/adapter_green_continue_step001800_hard4_fullframe/summary.json` | `25dcc8b6ce211682fadea85436e87b08ee888bb11607225ec7f75a14b0887822` |
| Mission GP017349 large-context step-900 hard4 summary | `artifacts/current_goal_sr_gp017349_large_context_20260619/adapter_green_continue_step000900_hard4_fullframe/summary.json` | `d005f120bc82d33c04750a0a8fa7c5b42a6348ccaaad6d3893701ea97895e177` |
| Mission rejected mixed large-context alpha-0.10 decision | `artifacts/current_goal_sr_mixed_large_context_hard4_20260619/mixed_large_context_alpha010_decision.json` | `41d4f01b5d943563816662db27f516261fd016c10ac1393384ef17431c9c5e3f` |
| Mission mixed large-context alpha-0.10 checkpoint | `artifacts/current_goal_sr_mixed_large_context_hard4_20260619/interp_mixed_to_gp017349_a100.pt` | `d962e481b4f9b165885ea3e634ca2ae291c3e4a44806e09422c503370aca5057` |
| Mission mixed large-context alpha-0.10 checkpoint sidecar | `artifacts/current_goal_sr_mixed_large_context_hard4_20260619/interp_mixed_to_gp017349_a100.pt.json` | `08ed6a79f9ac513daba2ac33467329ed71356c4c83f16756af5d6e1d74072f76` |
| Mission mixed hard4 large-context training checkpoint | `artifacts/current_goal_sr_mixed_large_context_hard4_20260619/adapter_green_mixed_hard4_large_context_w48_d6_rs03_1200.pt` | `79dfa0a2b090c4c7bfeb87427d7aec847842609c863f7f417e0ee2e558e3c9ce` |
| Mission mixed hard4 large-context training receipt | `artifacts/current_goal_sr_mixed_large_context_hard4_20260619/adapter_green_mixed_hard4_large_context_w48_d6_rs03_1200.pt.json` | `8b879c3fb28b4a83b7b3eea02507d26f1106ad47a939fc3ff045f548035379aa` |
| Mission mixed large-context hard4 full-frame summary | `artifacts/current_goal_sr_mixed_large_context_hard4_20260619/interp_a100_hard4_fullframe/summary.json` | `47368a6b7a7113f15d5a178532f12de2334d8d9d4f26d94f0164dbf0d590afc4` |
| Mission mixed large-context normal-current hard4 summary | `artifacts/current_goal_sr_mixed_large_context_hard4_20260619/interp_a100_normal_current_hard4_fullframe/summary.json` | `1ec618fde41ba1441ce6ca86c36f4662d86757e0ab8a7716906e23549fbb342c` |
| Mission mixed large-context Z8 holdout summary | `artifacts/current_goal_sr_mixed_large_context_hard4_20260619/interp_a100_z8_holdout5_fullframe/summary.json` | `31daa8792e0812f40cc10555308a4f835e585b728f64624519ce09dd5319f5ff` |

## Raw Stills Fixture Diagnostics

These rows are diagnostic. They strengthen the real-camera fixture search but
the latest broad old-photo scan closes the real GRBG/BGGR fixture gap when
combined with the GoPro/Mission scan. Mission/iPhone production darkframe stacks
remain open.

| artifact | path | sha256 |
|---|---|---|
| Targeted 2,000-file Bayer phase inventory JSON | `artifacts/bayer_phase_fixture_discovery_targeted_2000_20260630/inventory.json` | `dfef5e95c14c463efda9f1644201a235dc47df84cc87a3f536fd6cd3c38a230e` |
| Targeted 2,000-file Bayer phase dashboard | `artifacts/bayer_phase_fixture_discovery_targeted_2000_20260630/index.html` | `01a810fb0341b2a5a53c5863664f20b3a4a198debad49ee7cec7884e1f1ba505` |
| Targeted 3,000-file Bayer phase inventory JSON | `artifacts/bayer_phase_fixture_discovery_broad_dng_gpr_3000_20260630/inventory.json` | `7c69434fbd575e20596e2d26ee0dd7270e57eac87bea7dae6bfe36c94f252b80` |
| Targeted 3,000-file Bayer phase dashboard | `artifacts/bayer_phase_fixture_discovery_broad_dng_gpr_3000_20260630/index.html` | `edd17fd5c264dc9230cd272404b4180d9ca432f8ae38a32a183cb2d685b25055` |
| Source-root Bayer phase inventory JSON | `artifacts/bayer_phase_fixture_discovery_source_roots_20260630/inventory.json` | `f672d99a55e72eef4fb8f07865650c01d4db0b415ae74014455b756a456d7dc0` |
| Source-root Bayer phase dashboard | `artifacts/bayer_phase_fixture_discovery_source_roots_20260630/index.html` | `2f90700e137333c753a6cb12914836945503e8bf808ace63320f3252b3a1b5ca` |
| Broad old-photo Bayer phase inventory JSON | `artifacts/bayer_phase_fixture_discovery_broad_photos_20260701/inventory.json` | `2d73555e2d95f4b5bbd602c2be2ab66c3f6bccbb101c7f9e5a40fd2ef3aed1f2` |
| Broad old-photo Bayer phase dashboard | `artifacts/bayer_phase_fixture_discovery_broad_photos_20260701/index.html` | `19f3b402ec54f3eba27c8e02ffd83abe2f89978ac960e3700455425e707bcb42` |
| Targeted Mission DNG darkframe audit JSON | `artifacts/darkframe_candidate_audit_targeted_dng_20260630/darkframe_candidate_audit.json` | `dd06fb371f5177a03f2ffbc683e343f15f1286091b92eed053a2334f537dd74a` |
| Targeted Mission DNG darkframe dashboard | `artifacts/darkframe_candidate_audit_targeted_dng_20260630/index.html` | `dd7c607f07fa1b9f0f9e473ca514810b3adc74c22690359ae44a655256b2836a` |
| Full-manifest Mission/iPhone darkframe audit JSON | `artifacts/darkframe_candidate_audit_mission_iphone_fullmanifest_20260701/darkframe_candidate_audit.json` | `68523ecb35dc32342735e7843528d1a61fb7824e7c9f297934a611768425449e` |
| Full-manifest Mission/iPhone darkframe dashboard | `artifacts/darkframe_candidate_audit_mission_iphone_fullmanifest_20260701/index.html` | `bae377aeef9fa8f48947cb54d087af975b309b7315797616376db0ac785002a1` |
| Raw-stills noise sidecar readiness JSON | `artifacts/raw_stills_noise_sidecar_readiness_20260701/raw_stills_noise_sidecar_readiness.json` | `402980e03c440e89c7bc399808cd2bb87d72fdb175cf0bb71bffc76d2e4e7e92` |
| Raw-stills noise sidecar readiness dashboard | `artifacts/raw_stills_noise_sidecar_readiness_20260701/index.html` | `bbea0d5409cb7074f8a3babd2a5fc82de0b7322057b726023fc214653290a03d` |
| Raw-stills noise promotion gate JSON | `artifacts/raw_stills_noise_promotion_gate_20260702/raw_stills_noise_promotion_gate.json` | `442878809190061731cbb4d447b8c98e80a43de9fadcc5c460cf7e5d9975e822` |
| Raw-stills noise promotion gate dashboard | `artifacts/raw_stills_noise_promotion_gate_20260702/index.html` | `a7c6b307878bc315f1069a7b82aca2aee445fd8e6e1dd8376ba90dbc00a2057f` |
| Current stills fixture gap plan JSON | `artifacts/stills_fixture_gap_plan_noise_fullmanifest_20260701/stills_fixture_gap_plan.json` | `ecd791fd1b2405d2acc5e15c466bd5b67a9b9d002659a383c53d36a2c793f53a` |
| Current stills fixture gap plan dashboard | `artifacts/stills_fixture_gap_plan_noise_fullmanifest_20260701/index.html` | `01eceab64395920d6818dc9b524801d350bca2f5cd252e57f0deee9d2020bb7b` |
| Current raw-stills capture request JSON | `artifacts/stills_capture_request_strict_provenance_20260701/stills_capture_request.json` | `a6dfad28cf05b771226614c4a6316fbec7bcfec7b91e6347c959db0decc762c2` |
| Current raw-stills capture request dashboard | `artifacts/stills_capture_request_strict_provenance_20260701/index.html` | `c067a6faa811908c19bfd6c99ac70ac75dcc653251d4bba4c9d31233a096f5b1` |
| Mission/iPhone darkframe provenance packet JSON | `artifacts/darkframe_provenance_review_packet_100_percent_20260702/darkframe_provenance_review_packet.json` | `52d825deb046a0bbb90e457759e39c32da8ecf3d7c607441b6562e67a75b9b7e` |
| Mission/iPhone darkframe provenance packet dashboard | `artifacts/darkframe_provenance_review_packet_100_percent_20260702/index.html` | `d962acd4425f712c0e4aa5ffbf9c5ed703b4b6a707a31e40d5ca36b4521381dd` |
| Mission/iPhone darkframe extraction progress JSON | `artifacts/darkframe_provenance_review_packet_100_percent_20260702/darkframe_extraction_progress.json` | `a7dc40baf4b53e35fae2ff7f8017f336e0d9d1e61c2ec5451fb2fbf4cd0e62cc` |
| RAW-stills noise blocker audit JSON | `artifacts/raw_stills_noise_blocker_audit_20260702/raw_stills_noise_blocker_audit.json` | `e130a82586330a2d108e569cffc0e0a9715a4f0f5869655301357cefa6ad5178` |
| RAW-stills noise blocker audit dashboard | `artifacts/raw_stills_noise_blocker_audit_20260702/index.html` | `64ce5cfe59734f1300806df8f916cb3518d45c8c0402549a0209870185d7ce26` |
| 100 percent product burn-down queue JSON | `artifacts/product_burndown_100_percent_queue_20260702/product_burndown.json` | `1f6f5b8c53b3fd23e04144789f6b6a4d3edad29505450202bad761510418b941` |
| 100 percent product burn-down queue dashboard | `artifacts/product_burndown_100_percent_queue_20260702/index.html` | `046ee586ff241f23f53f56eacf0b683389cfa15b051408b294a8c95e36cb0438` |
| iPhone darkframe provenance template | `artifacts/darkframe_provenance_review_packet_100_percent_20260702/source_provenance_manifest_templates/iphone_cfa_darkframe_stack__Apple_iPhone_7_Plus_ISO1250_RGGB.template.json` | `f6a95718ca973acb89467a99de97c2cadfbe91158305092874407f66dfe2abdd` |
| Mission 1 darkframe provenance template | `artifacts/darkframe_provenance_review_packet_100_percent_20260702/source_provenance_manifest_templates/mission1_darkframe_stack__GoPro_MISSION_1_ISO232_RGGB.template.json` | `51b649476055a12268e6a661bf536e3e79d99c123b7ca1ef621beb10c7ac8079` |

## Premium Still-SR Gap Artifacts

These rows are diagnostic, not production promotion receipts. They preserve the
current raw-CFA residual blocker state for the spend-time-for-quality still/SR
pillar.

| artifact | path | sha256 |
|---|---|---|
| Premium still-SR experiment scoreboard JSON | `artifacts/premium_still_sr_experiment_scoreboard_restormer_degrade_t64_20260702/scoreboard.json` | `bf3d435931c2c526a9b73852d10745940b1c92f98dafb4511d1a03097e4f5d1e` |
| Premium still-SR experiment scoreboard dashboard | `artifacts/premium_still_sr_experiment_scoreboard_restormer_degrade_t64_20260702/index.html` | `858c7790b7729441cb95cd34f79425c60481545150cf27da2b3c6fb95ea9c14c` |
| Premium still-SR full X2D window-attention receipt | `artifacts/premium_still_sr_window_attention_teacher_gate_20260701/x2d_scene_holdout_window_attention_teacher_cfa/train_receipt.json` | `cf22244dc3e9a2c97e62b735363b92347f4cc43985a476897bb8546c6c982d95` |
| Premium still-SR full X2D window-attention dashboard | `artifacts/premium_still_sr_window_attention_teacher_gate_20260701/x2d_scene_holdout_window_attention_teacher_cfa/index.html` | `e9b8265055965091e71c0eaf4dda201091b019ed93c31342d3eb811667360961` |
| Premium still-SR full X2D window-attention checkpoint | `artifacts/premium_still_sr_window_attention_teacher_gate_20260701/x2d_scene_holdout_window_attention_teacher_cfa/premium_still_sr_window_attention_x2d_holdout_cfa.pt` | `a853cf2daffeb29ddc0cc0b891f4c9f5926c7bad5b610b8b7628c960843f6a6b` |
| Premium still-SR signal-objective contract JSON | `artifacts/premium_still_sr_signal_objective_gate_20260701/premium_still_sr_next_experiment_contract.json` | `cf072e65663ab07d4ee0fef507ba7b1be1e8be1f1a37a3931653334a91ac8b9f` |
| Premium still-SR signal-objective dashboard | `artifacts/premium_still_sr_signal_objective_gate_20260701/index.html` | `f587b5c11d333cfb14d569046fa73856b31f7e3ef4a6d4d98cae292beb072d80` |
| Premium still-SR X2D signal-learnability audit JSON | `artifacts/premium_still_sr_signal_objective_gate_20260701/x2d_scene_holdout_signal_learnability/candidate_signal_audit.json` | `0ebeafa00f71b4a7947e9ff1d8326eb7c4eb8915bee1c5a56cdabae7a699b745` |
| Premium still-SR X2D signal-learnability dashboard | `artifacts/premium_still_sr_signal_objective_gate_20260701/x2d_scene_holdout_signal_learnability/index.html` | `566a60cc184440e27592bb81de0869f2817ac6fac34704baf943a3aa57bc5fd9` |
| Premium still-SR Z8 signal-learnability audit JSON | `artifacts/premium_still_sr_signal_objective_gate_20260701/z8_scene_holdout_signal_learnability/candidate_signal_audit.json` | `c1839471d62069215106cbc7a43ba850b80f9e4350f2a577a8de744fc5ca1594` |
| Premium still-SR Z8 signal-learnability dashboard | `artifacts/premium_still_sr_signal_objective_gate_20260701/z8_scene_holdout_signal_learnability/index.html` | `fac124ac29be071983ccc93bfae8b901258b5b859ab8813a87f89a51a2296fa1` |
| Premium still-SR clean-signal target JSON | `artifacts/premium_still_sr_clean_signal_targets_20260702/clean_signal_targets.json` | `61d6ad8f19a66a6221aea26fe7dc1dafa06c97cfc3de34c88fb48606d5f27a21` |
| Premium still-SR clean-signal target dashboard | `artifacts/premium_still_sr_clean_signal_targets_20260702/index.html` | `83b7ce1ae7cac8767bf8f0dea232ec457e463f864b0717d9f8a1feafab779eb2` |
| Premium still-SR clean-signal X2D learnability JSON | `artifacts/premium_still_sr_clean_signal_targets_20260702/x2d_clean_signal_learnability/candidate_signal_audit.json` | `1c54d9e28d4d8e7ef591fe4270cd72c09f0f4c0636169beb962477bdb39d8136` |
| Premium still-SR clean-signal X2D learnability dashboard | `artifacts/premium_still_sr_clean_signal_targets_20260702/x2d_clean_signal_learnability/index.html` | `a74897dd7c03bccf600e2efc8f7c5524678a547db581c489f2a0a1da3ee83f85` |
| Premium still-SR clean-signal Z8 learnability JSON | `artifacts/premium_still_sr_clean_signal_targets_20260702/z8_clean_signal_learnability/candidate_signal_audit.json` | `ee4cf33dea5aa6c7be38920d09bf736c4b1a4b4b2b92984356ceb43cc3b58c00` |
| Premium still-SR clean-signal Z8 learnability dashboard | `artifacts/premium_still_sr_clean_signal_targets_20260702/z8_clean_signal_learnability/index.html` | `d5d21c2d84945f41c15eb44ab0dbe4ab9fac2047926d793d7a09a830019febcb` |
| Premium still-SR clean-signal SNR audit JSON | `artifacts/premium_still_sr_clean_signal_targets_20260702/clean_signal_snr_audit/raw_target_snr_audit.json` | `de5c690fcd0d7a794d58ef314dc5653ce38a1652eb5e3f81a866e1827d58ab8d` |
| Premium still-SR clean-signal SNR dashboard | `artifacts/premium_still_sr_clean_signal_targets_20260702/clean_signal_snr_audit/index.html` | `aeb6f2c5f57efa901cc9346e99cc0573c7abe4d15766e1330b9579030eee0643` |
| Premium still-SR clean-signal U-Net rejection receipt | `artifacts/premium_still_sr_clean_signal_model_x2dsceneholdout_unet_w32_700_20260702/train_receipt.json` | `abb7e0775fb0de7c05d3bff792fc618d39dc12adb0713701d84a9aa94bce9d1c` |
| Premium still-SR clean-signal U-Net rejection dashboard | `artifacts/premium_still_sr_clean_signal_model_x2dsceneholdout_unet_w32_700_20260702/index.html` | `dcb6f26f67848c43894d59e0ec0b8742d8b1dc62242625085a8faf19cca9b0a8` |
| Premium still-SR current self-supervised RAW SR contract JSON | `artifacts/premium_still_sr_self_supervised_raw_sr_contract_20260702/premium_still_sr_next_experiment_contract.json` | `d79bdd20ac54ed3217bf64fa6b4746468af519d868045d840aef6da6ff84dde1` |
| Premium still-SR current self-supervised RAW SR contract dashboard | `artifacts/premium_still_sr_self_supervised_raw_sr_contract_20260702/index.html` | `1fee33dc0859271479053de451cea2639b06121856a291d9d66af8d23803e238` |
| Premium still-SR clean-source RAW SR pair smoke NPZ | `artifacts/premium_still_sr_self_supervised_raw_sr_pairs_smoke_20260702/premium_still_sr_clean_source_pairs_smoke.npz` | `a0c8a396fda09fdc76d58ef44c8bec17f557a3789c4595ec3d19cfb12a129f5c` |
| Premium still-SR clean-source RAW SR pair smoke metadata | `artifacts/premium_still_sr_self_supervised_raw_sr_pairs_smoke_20260702/premium_still_sr_clean_source_pairs_smoke.npz.json` | `0b7d04c6002520d9979f04e78348393feb70cabc64a1a27c70f981f4f54814f2` |
| Premium still-SR clean-source RAW SR pair audit JSON | `artifacts/premium_still_sr_self_supervised_raw_sr_pair_audit_smoke_20260702/pair_audit.json` | `a492de1019370da2e17ea8917755ede0a634cdda74cb65688a8b375311c3eb78` |
| Premium still-SR clean-source RAW SR pair audit dashboard | `artifacts/premium_still_sr_self_supervised_raw_sr_pair_audit_smoke_20260702/index.html` | `4fe947ef8450bcfdd83fd62a1c957af2e0a2819e98dc60c9542d8f00089ea7dc` |
| Premium still-SR clean-source pair model smoke receipt | `artifacts/premium_still_sr_clean_source_pair_model_smoke_20260702/train_receipt.json` | `a7c9ce3ac56662e7701b8324b45847b1629506a1224a80aceb0aab386271a85a` |
| Premium still-SR clean-source pair model smoke dashboard | `artifacts/premium_still_sr_clean_source_pair_model_smoke_20260702/index.html` | `613db125e2eac7691504b43ba0af7157e3ee4965d6487e5a933eadce821e45cc` |
| Premium still-SR clean-source pair model smoke checkpoint | `artifacts/premium_still_sr_clean_source_pair_model_smoke_20260702/premium_still_sr_clean_source_pair_model.pt` | `5c516db53755ede6c9d3c1923c8ae2d9f27c88cbe98740af402b16643803ef38` |
| Premium still-SR routed clean-source RAW SR pair NPZ | `artifacts/premium_still_sr_self_supervised_raw_sr_pairs_routed_t16_20260702/premium_still_sr_clean_source_pairs_routed_t16.npz` | `53e7bb8b601a1156c3d1f3acb1bcc0ea0b9ff80b81fb734059a8dd9a3e745443` |
| Premium still-SR routed clean-source RAW SR pair metadata | `artifacts/premium_still_sr_self_supervised_raw_sr_pairs_routed_t16_20260702/premium_still_sr_clean_source_pairs_routed_t16.npz.json` | `56e271e6fa9ce853545972a50e39d4dd33be27d1fd491908b003f64623f283d6` |
| Premium still-SR routed clean-source RAW SR pair audit JSON | `artifacts/premium_still_sr_self_supervised_raw_sr_pair_audit_routed_t16_20260702/pair_audit.json` | `98a5bb0a2e7c67ec422ff7118376e02769bf2eca142baaeeb12ca5cabee2d111` |
| Premium still-SR routed clean-source RAW SR pair audit dashboard | `artifacts/premium_still_sr_self_supervised_raw_sr_pair_audit_routed_t16_20260702/index.html` | `cfb7c5ccf6f93631a267085373e6ae8929d6c5980197667add60d62771aecd17` |
| Premium still-SR routed X2D holdout rejection receipt | `artifacts/premium_still_sr_clean_source_pair_model_routed_x2dholdout_w48_1500_20260702/train_receipt.json` | `c7dc2ed29aacb410126e2949ab8d54bb97e5d02ce8455fe8c56c8d6d529a0e4c` |
| Premium still-SR routed X2D holdout rejection dashboard | `artifacts/premium_still_sr_clean_source_pair_model_routed_x2dholdout_w48_1500_20260702/index.html` | `a154652069efbebcde7983c4ae789b6a078a23ebfc6e56500d584db73e36c723` |
| Premium still-SR routed X2D holdout rejection checkpoint | `artifacts/premium_still_sr_clean_source_pair_model_routed_x2dholdout_w48_1500_20260702/premium_still_sr_clean_source_pair_model.pt` | `e2d015e1d33b0cf4aa92cc24b7e577ebe9d1fa140669006f45020e17ee253855` |
| Premium still-SR routed Z8 holdout rejection receipt | `artifacts/premium_still_sr_clean_source_pair_model_routed_z8holdout_w48_1500_20260702/train_receipt.json` | `bad6848ed26ad07c3677343c8f39a75bbb349c4a71e7e387e8c4ab24cefa1f3e` |
| Premium still-SR routed Z8 holdout rejection dashboard | `artifacts/premium_still_sr_clean_source_pair_model_routed_z8holdout_w48_1500_20260702/index.html` | `01c799d87dae0489d01c090145c8fe0b69fcdb742b7770380f3b4fa26d2e6bb6` |
| Premium still-SR routed Z8 holdout rejection checkpoint | `artifacts/premium_still_sr_clean_source_pair_model_routed_z8holdout_w48_1500_20260702/premium_still_sr_clean_source_pair_model.pt` | `5ec00d33900be5c18f90876fbec754d1ec154e76d92b7eb31656c54784d389ea` |
| Premium still-SR routed NAF/detail X2D rejection receipt | `artifacts/premium_still_sr_clean_source_pair_model_routed_x2dholdout_naf_grad_w48_500_20260702/train_receipt.json` | `47fecf0b55a2282ce965bc5ac5929b2cf5c168730348f6f99765cd0f3e88cdcb` |
| Premium still-SR routed NAF/detail X2D rejection dashboard | `artifacts/premium_still_sr_clean_source_pair_model_routed_x2dholdout_naf_grad_w48_500_20260702/index.html` | `0159756c9d009e0d72030e6f1f90d9bb6a1f470d9915a44a5a75fc5465ed7e09` |
| Premium still-SR routed NAF/detail X2D rejection checkpoint | `artifacts/premium_still_sr_clean_source_pair_model_routed_x2dholdout_naf_grad_w48_500_20260702/premium_still_sr_clean_source_pair_model.pt` | `b50d3f76ca917ba494d1481928c0c1ffc0cb30887bb2f1d3204f86e1fd38820a` |
| Premium still-SR routed NAF/detail Z8 rejection receipt | `artifacts/premium_still_sr_clean_source_pair_model_routed_z8holdout_naf_grad_w48_500_20260702/train_receipt.json` | `d7bae678f565ddb2b0b9c798ec35d85293948973660b91544e2e9d3c4146c9b2` |
| Premium still-SR routed NAF/detail Z8 rejection dashboard | `artifacts/premium_still_sr_clean_source_pair_model_routed_z8holdout_naf_grad_w48_500_20260702/index.html` | `384190890479e0fac9b5c5b2f316e506595cabae595d6dfdce42adefae30c192` |
| Premium still-SR routed NAF/detail Z8 rejection checkpoint | `artifacts/premium_still_sr_clean_source_pair_model_routed_z8holdout_naf_grad_w48_500_20260702/premium_still_sr_clean_source_pair_model.pt` | `d904f1ea020b954bb77844199fc06cb8b8687cfe7bc12c37a94faf11febd726a` |
| Premium still-SR noise-policy gate receipt | `artifacts/premium_still_sr_noise_policy_gate_20260702/premium_still_sr_noise_policy_gate.json` | `63805263c173a37434fc8f79ef1abdf2e3c292d98a396766370790e038a64475` |
| Premium still-SR noise-policy gate dashboard | `artifacts/premium_still_sr_noise_policy_gate_20260702/index.html` | `d90b74c5d864b13b51ea429955e1776be39cb040254e3ff71407449f62c5044d` |
| Premium still-SR promotion gate receipt | `artifacts/premium_still_sr_promotion_gate_20260702/premium_still_sr_promotion_gate.json` | `6a4b74bf24d59b79b08b2873bc3ab330070a4024b0c9eb091d8d373db25634d7` |
| Premium still-SR promotion gate dashboard | `artifacts/premium_still_sr_promotion_gate_20260702/index.html` | `c3ba02586a9aaa34c11b130f0f52b91b3aa15a6c4bb05a0251cf6d7396c46a0b` |
| Premium still-SR raw-CFA residual gap JSON | `artifacts/premium_still_sr_raw_cfa_residual_gap_20260701/raw_cfa_residual_gap.json` | `3d95db1c9c468034e11ef255d3f3606fb5546e4a77b0d7eb49b8b82d11aaad13` |
| Premium still-SR raw-CFA residual gap dashboard | `artifacts/premium_still_sr_raw_cfa_residual_gap_20260701/index.html` | `ba0ddcc00db1f9b22d2e3c138051cbd375a6a5c6b78f87f9ab623e7ade062968` |
| Premium still-SR candidate-signal ridge audit JSON | `artifacts/premium_still_sr_candidate_signal_x2dholdout_20260630/candidate_signal_audit.json` | `0ff547e2b3eac9790ded2794f1ae2791438f1b6f309690c9f9c111d1b0d98967` |
| Premium still-SR candidate-signal ridge audit dashboard | `artifacts/premium_still_sr_candidate_signal_x2dholdout_20260630/index.html` | `e3d14168594271f93461610e2efc88e85f271f1fe5efd5ad27e70ca1b43acdac` |
| Premium still-SR X2D same-scene center candidate-signal audit JSON | `artifacts/premium_still_sr_candidate_signal_x2d1742_center_same_scene_20260701/candidate_signal_audit.json` | `eeff361e82e78fef67a5444ceb3148bba1f607d5ee0523e0511213c2130d318c` |
| Premium still-SR X2D same-scene center candidate-signal dashboard | `artifacts/premium_still_sr_candidate_signal_x2d1742_center_same_scene_20260701/index.html` | `24714e4faf5d2e67ef5e0acfd6f479c6c859712ac44fcb24ae5a2e6a3a493af3` |
| Premium still-SR X2D same-scene frequency-filter audit JSON | `artifacts/premium_still_sr_frequency_filter_x2d1742_center_same_scene_20260701/frequency_filter_audit.json` | `3d90c9539353e6d584d3eeaa1fdef74294f04ed3be0c5f8dc7742b1cd247c6f2` |
| Premium still-SR X2D same-scene frequency-filter dashboard | `artifacts/premium_still_sr_frequency_filter_x2d1742_center_same_scene_20260701/index.html` | `5ff5d372cb16116ec715097ebafff1b5a0925d616d1f8f068e8df2421096dc81` |
| Premium still-SR raw target duplicate audit JSON | `artifacts/premium_still_sr_raw_target_duplicate_audit_20260701/raw_target_duplicate_audit.json` | `4914096083d6720ba564d675fba4c7dfbfbaaf26d58dd1215b15a4b372f1b5d1` |
| Premium still-SR raw target duplicate dashboard | `artifacts/premium_still_sr_raw_target_duplicate_audit_20260701/index.html` | `1ef2f96c803580ab078ddefad90d22856c380b867333e5b38d0c95d376787fc6` |
| Premium still-SR CFA-aware raw-CFA target NPZ | `artifacts/premium_still_sr_raw_cfa_residual_targets_cfa_20260701/raw_cfa_residual_targets.npz` | `06fa4b4efdc04b946a596d6907f79d590b62c0969716f903f3edcbd6be9a3488` |
| Premium still-SR CFA-aware raw-CFA target JSON | `artifacts/premium_still_sr_raw_cfa_residual_targets_cfa_20260701/raw_cfa_residual_targets.json` | `9b3d4bb8f74ddddcef902fe5b1c36a537aa115692f796b404f1fed4d1110451f` |
| Premium still-SR CFA-aware raw-CFA target dashboard | `artifacts/premium_still_sr_raw_cfa_residual_targets_cfa_20260701/index.html` | `7cfff7f48f1fb2428956736b68e20229a44648924fcb5864be90c354a02b16ff` |
| Premium still-SR deduplicated CFA-aware raw-CFA target NPZ | `artifacts/premium_still_sr_raw_cfa_residual_targets_dedup_cfa_20260701/raw_cfa_residual_targets_dedup.npz` | `3589262e9d4c12a399fd66c4041ac12c12b0be72413a2b0c154be5317a2f5442` |
| Premium still-SR deduplicated CFA-aware raw-CFA target JSON | `artifacts/premium_still_sr_raw_cfa_residual_targets_dedup_cfa_20260701/raw_cfa_residual_targets_dedup.json` | `1bd35991823fe50ef6b6db9c097f35e2c383dcf46ac5d83bbd6863ad2c8d97d3` |
| Premium still-SR deduplicated CFA-aware raw-CFA target dashboard | `artifacts/premium_still_sr_raw_cfa_residual_targets_dedup_cfa_20260701/index.html` | `e78420c9ecfbf485d9877722bcafa1e57279b5b1ef6d47a2839dec13dcc80a3c` |
| Premium still-SR deduped RCAB teacher smoke checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_dedup_rcab_teacher_smoke_20260701/premium_still_sr_raw_cfa_residual_dedup_rcab_teacher_smoke.pt` | `c77b17a5bb66265061d449e17950c54f79837bfcda3a225fdf0bd26cedacac0b` |
| Premium still-SR deduped RCAB teacher smoke receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_dedup_rcab_teacher_smoke_20260701/train_receipt.json` | `1644f000d4dac763896eaf29934cad9f56e1da529c6fed1a94e4145ab2ab9a5b` |
| Premium still-SR deduped RCAB teacher smoke dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_dedup_rcab_teacher_smoke_20260701/index.html` | `17e509a8d4cbaabf54b53d835657b145e5fa3bf05fe692eb59e688293ecfd8c4` |
| Premium still-SR deduped RCAB teacher smoke panel | `artifacts/premium_still_sr_raw_cfa_residual_model_dedup_rcab_teacher_smoke_20260701/panel_sheet.jpg` | `b324e92d8f2c7092790bcdcad83f8e7589e869b8dede7da4083f6eec89f5928a` |
| Premium still-SR scaled RCAB teacher checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_dedup_rcab_teacher_w32_700_20260701/premium_still_sr_raw_cfa_residual_dedup_rcab_teacher_w32_700.pt` | `d4ae79ea7aac0a3a92f546cc618cd94f38765493e300de19333105a3bc475473` |
| Premium still-SR scaled RCAB teacher receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_dedup_rcab_teacher_w32_700_20260701/train_receipt.json` | `d6f27598e11a2f6f5df4665a8f707e2e18b165b4edfb7d479a2d6de02584bc39` |
| Premium still-SR scaled RCAB teacher dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_dedup_rcab_teacher_w32_700_20260701/index.html` | `de84f13bf887a6b35c915c7e04fe36cfdaba51d4609133efc4577227a4eb6853` |
| Premium still-SR scaled RCAB teacher panel | `artifacts/premium_still_sr_raw_cfa_residual_model_dedup_rcab_teacher_w32_700_20260701/panel_sheet.jpg` | `0e74a3aac18e9c91fabd02c3cdc543774eeea6dcbd1e95b8a857b35eb0a730dd` |
| Premium still-SR simple NAF teacher checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_dedup_naf_teacher_w32_700_20260701/premium_still_sr_raw_cfa_residual_dedup_naf_teacher_w32_700.pt` | `c636ccfdc490f8fc59249a3f88042a331758881d3aced3ce273b8f95d364488b` |
| Premium still-SR simple NAF teacher receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_dedup_naf_teacher_w32_700_20260701/train_receipt.json` | `0cb0d589f47d491b56afa150170e79a4cad589915714f34758a828c04b0d9e59` |
| Premium still-SR simple NAF teacher dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_dedup_naf_teacher_w32_700_20260701/index.html` | `db8131cda2e60ca4040dd7eae3db844149de51b07f849829eb240bd029f4b152` |
| Premium still-SR simple NAF teacher panel | `artifacts/premium_still_sr_raw_cfa_residual_model_dedup_naf_teacher_w32_700_20260701/panel_sheet.jpg` | `e85529f90863875be5be43cd4d0b03a3eda3a87e2866b3ae0bd3b37be94a1e34` |
| Premium still-SR corrected-distribution X2D NAF checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_naf_teacher_w32_700_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_naf_teacher_w32_700.pt` | `62c4f9be4d006ae78efec9cc89cd60b27ad805297b0e473768a32dd37768b275` |
| Premium still-SR corrected-distribution X2D NAF receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_naf_teacher_w32_700_20260701/train_receipt.json` | `c6f16689328eb39d44bef0e6e5df863a4a800a8b3302627cb8c84e4c076396ac` |
| Premium still-SR corrected-distribution X2D NAF dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_naf_teacher_w32_700_20260701/index.html` | `fffb4468a6c9c7f7282906c668c6df761f44caff4d2264c12a7fa36deb31032c` |
| Premium still-SR corrected-distribution X2D NAF panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_naf_teacher_w32_700_20260701/panel_sheet.jpg` | `a9d345b893382cd3787cdcdf3296e5db61dd5b65486bd192f6b09f774f569cd1` |
| Premium still-SR signal-only X2D U-Net checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrfiltered_unet_w32_1200_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_snrfiltered_unet_w32_1200.pt` | `f91a8b73048d71250c9e34dc34500959d1b16237e45ce587f688c02ac54c12a2` |
| Premium still-SR signal-only X2D U-Net receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrfiltered_unet_w32_1200_20260701/train_receipt.json` | `1b24444e6165751eb9faf57fd9556f8f222a0d742050f55969f0b4e188e7ac92` |
| Premium still-SR signal-only X2D U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrfiltered_unet_w32_1200_20260701/index.html` | `0e28f6c96566f37ee7f28c185688539020e14797924a5526b6b655499eaca898` |
| Premium still-SR signal-only X2D U-Net panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrfiltered_unet_w32_1200_20260701/panel_sheet.jpg` | `d22c7da951d6bc3affa07b52208ee4600df4988bc3adaf6e37f4af793b04185a` |
| Premium still-SR signal-or-mixed X2D U-Net checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrmixed_unet_w32_1200_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_snrmixed_unet_w32_1200.pt` | `cc06bebc273ee73b2357e2c3206790e4594cd2874bd01ab72e7a195a371576ba` |
| Premium still-SR signal-or-mixed X2D U-Net receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrmixed_unet_w32_1200_20260701/train_receipt.json` | `44d4c300ce6da77c3b837904f6b0b6e8591493aa90fc07f3b94548bb95dd298b` |
| Premium still-SR signal-or-mixed X2D U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrmixed_unet_w32_1200_20260701/index.html` | `654f0990a40c8eae2d8eb3bf4d9c1bef85b995505d3c6bc4b72960066b02e669` |
| Premium still-SR signal-or-mixed X2D U-Net panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrmixed_unet_w32_1200_20260701/panel_sheet.jpg` | `41efa0424523d54831bf20a3441dbca4f7108ca7f8dcf75624aecff0e9c981a2` |
| Premium still-SR unfiltered X2D U-Net checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_x2dall_unet_w32_1200_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_x2dall_unet_w32_1200.pt` | `cca7eb4b90b8e2a1cef297702501addcddfef7d2c7727dfe4a46c896d1df9bf3` |
| Premium still-SR unfiltered X2D U-Net receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_x2dall_unet_w32_1200_20260701/train_receipt.json` | `902075a9ef094851ea3a8304eb731749920fcbef2fcccb3468bafeeb1c3a6297` |
| Premium still-SR unfiltered X2D U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_x2dall_unet_w32_1200_20260701/index.html` | `52cca636c083318b82cac1e919abc015ea4b2c275ba6c4fe90af629147399d66` |
| Premium still-SR unfiltered X2D U-Net panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_x2dall_unet_w32_1200_20260701/panel_sheet.jpg` | `0ce02403431b50fbafd07bef4c7a1e95b515277e2929d0a2d6d6e61c56c71ed3` |
| Premium still-SR signal-emphasis weighted X2D U-Net checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_signal_unet_w32_1200_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_snrweighted_signal_unet_w32_1200.pt` | `31b246efe27b58cbb7f472a5a47f50520cafde3fdb97419b38f6e16544fb4cd8` |
| Premium still-SR signal-emphasis weighted X2D U-Net receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_signal_unet_w32_1200_20260701/train_receipt.json` | `830116b2a02f8ed9d3ef057c4444b7ec19f3ae1af04fd5451605521a11f40fdb` |
| Premium still-SR signal-emphasis weighted X2D U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_signal_unet_w32_1200_20260701/index.html` | `23ceff82370dbb05d61e5ff494405954d948c9d62579624d7e99873f789abc73` |
| Premium still-SR signal-emphasis weighted X2D U-Net panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_signal_unet_w32_1200_20260701/panel_sheet.jpg` | `3515491f2a1185bf3fffe67f38d2255b3e3e97b60e3986b72e0598be82b66844` |
| Premium still-SR continuous-SNR weighted X2D U-Net checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_continuous_unet_w32_1200_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_snrweighted_continuous_unet_w32_1200.pt` | `407485105d07210417ca3b1520190a5da5863e2c54faec50a526fb430d75291c` |
| Premium still-SR continuous-SNR weighted X2D U-Net receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_continuous_unet_w32_1200_20260701/train_receipt.json` | `ceb4bd643c59236a0da995fd3f94a6e5b2d19f2711b241f46cf1abcd77cc7273` |
| Premium still-SR continuous-SNR weighted X2D U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_continuous_unet_w32_1200_20260701/index.html` | `c4b51d17200f17e67a6a6dabb3eb8784eef1bf915b2dd65f3e5df51e438d8c67` |
| Premium still-SR continuous-SNR weighted X2D U-Net panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_continuous_unet_w32_1200_20260701/panel_sheet.jpg` | `5b69dfd794475f28b116b9d8692f9c4fd9b5fe60ed8d74d53ddffb8962965a6c` |
| Premium still-SR noise-floor weighted X2D U-Net checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_noisefloor_unet_w32_1200_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_snrweighted_noisefloor_unet_w32_1200.pt` | `65c0cfea3bf5656942a7005d1a3879fae6cb60b627f2255fdde566a44c55cdfb` |
| Premium still-SR noise-floor weighted X2D U-Net receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_noisefloor_unet_w32_1200_20260701/train_receipt.json` | `bb3b67139e200561e846db587c3b682af0d348b68fd0d2b55352f7782fbfa4aa` |
| Premium still-SR noise-floor weighted X2D U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_noisefloor_unet_w32_1200_20260701/index.html` | `fb78c10a5ded7e19426c2fd5b01c6402368561b2865b2267582fdf338e047c45` |
| Premium still-SR noise-floor weighted X2D U-Net panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_noisefloor_unet_w32_1200_20260701/panel_sheet.jpg` | `14a5a06865f281d2dad6ade0e1b7921fb5c5168e1354bbb1b62dd2b61ed440c7` |
| Premium still-SR CFA-target non-CFA control checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_cfa_target_control_unet_w32_1200_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_cfa_target_control_unet_w32_1200.pt` | `5e5f2700e513d48d177788cd8ea70fba0bc165daa1fa29662db13de4addbeffa` |
| Premium still-SR CFA-target non-CFA control receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_cfa_target_control_unet_w32_1200_20260701/train_receipt.json` | `c02652a8e10796500e642a8f49ac009c8a0dd2283c5a37c8522a0ce6a8dedb87` |
| Premium still-SR CFA-target non-CFA control dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_cfa_target_control_unet_w32_1200_20260701/index.html` | `2109e5f0c0334ea34fe62e428f866a184cf118dd458902b013ceb6048e66a2e6` |
| Premium still-SR CFA-target non-CFA control panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_cfa_target_control_unet_w32_1200_20260701/panel_sheet.jpg` | `14a5a06865f281d2dad6ade0e1b7921fb5c5168e1354bbb1b62dd2b61ed440c7` |
| Premium still-SR CFA-conditioned matched X2D U-Net checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_cfa_matched_unet_w32_1200_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_cfa_matched_unet_w32_1200.pt` | `8670d58386ffe32c28a655d15a001fba7b3ae648062a80857d3fdec2673d4514` |
| Premium still-SR CFA-conditioned matched X2D U-Net receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_cfa_matched_unet_w32_1200_20260701/train_receipt.json` | `53b81d7f07e28f2868921b7621b2a201bc138aafba11127acdc04bd1f6607b54` |
| Premium still-SR CFA-conditioned matched X2D U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_cfa_matched_unet_w32_1200_20260701/index.html` | `0df200450f58877c58fc99fca8b7f965cd1daf3aee04722310eeda0cf86c6ce5` |
| Premium still-SR CFA-conditioned matched X2D U-Net panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_cfa_matched_unet_w32_1200_20260701/panel_sheet.jpg` | `15d00c0799e6b17f712429fb0ac7f02a162fd8d451b454894fcea30ada326d6f` |
| Premium still-SR matched global-context X2D U-Net checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_globalctx_matched_w32_1200_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_globalctx_matched_w32_1200.pt` | `063434de4bc689e9132c32f75125eb2307e398cc8dfe15bf4961d2969b738afe` |
| Premium still-SR matched global-context X2D U-Net receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_globalctx_matched_w32_1200_20260701/train_receipt.json` | `bb2b197f9959fc845fb766120eb89296a18d3e296bfaa36f00e64b4ce4eddd8d` |
| Premium still-SR matched global-context X2D U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_globalctx_matched_w32_1200_20260701/index.html` | `c434b8ceab86b788ef1ef01983e1a2dd2a2a4e1017180e7822046a9c1c5324d2` |
| Premium still-SR matched global-context X2D U-Net panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_globalctx_matched_w32_1200_20260701/panel_sheet.jpg` | `b373f77b519a42bbc6c517bb0230cbf82d4e623897ccdbc8182ecfc9c0f42a17` |
| Premium still-SR non-box PSF/CFA NAF X2D checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_nonboxpsf_cfa_naf_w32_800_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_nonboxpsf_cfa_naf_w32_800.pt` | `bb327124e03989f8d539815fd1722128dc0937ae23dd56f126da50bee36bd8cf` |
| Premium still-SR non-box PSF/CFA NAF X2D receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_nonboxpsf_cfa_naf_w32_800_20260701/train_receipt.json` | `c04ce9f3be5b2e03afbc4145a966cdeef53793fe8f7d3fc2d7831a1fe07f57bf` |
| Premium still-SR non-box PSF/CFA NAF X2D dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_nonboxpsf_cfa_naf_w32_800_20260701/index.html` | `5cc3d6fe78c842ce679be34133825b6d2986f993c3eb7e944c40704772b2b6d1` |
| Premium still-SR non-box PSF/CFA NAF X2D panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_nonboxpsf_cfa_naf_w32_800_20260701/panel_sheet.jpg` | `140b427369c204310d68a8d3b7aeef6e5eb146725c7aa1bb74877c4de9898847` |
| Premium still-SR stored-HF noise-floor X2D U-Net checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_storedhf_noisefloor_unet_w32_1200_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_storedhf_noisefloor_unet_w32_1200.pt` | `e80d02c5ed52bee00383fbda66d34b54acc9ac6f628583da69fd07a1dbf81d1b` |
| Premium still-SR stored-HF noise-floor X2D U-Net receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_storedhf_noisefloor_unet_w32_1200_20260701/train_receipt.json` | `1f1a1661109fb7867bce084a5973c8c25cad4f91b7c57ad9f5c3f7457ce6c80a` |
| Premium still-SR stored-HF noise-floor X2D U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_storedhf_noisefloor_unet_w32_1200_20260701/index.html` | `90b8af514b1be793ab30dc0ffdea83d2eaee6fd7fdb6c37143d7e3beba666b82` |
| Premium still-SR stored-HF noise-floor X2D U-Net panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_storedhf_noisefloor_unet_w32_1200_20260701/panel_sheet.jpg` | `9e13e11b010c1bd2e55a0ffc04aacc5d44c9aa0900b163271784a2e9c8f87616` |
| Premium still-SR pyramid noise-floor X2D U-Net checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_noisefloor_pyramid_unet_w32_1200_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_noisefloor_pyramid_unet_w32_1200.pt` | `152c3e1ccd8254c925406f9241668a963b87467985367dcff63d63aaad8d4cc5` |
| Premium still-SR pyramid noise-floor X2D U-Net receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_noisefloor_pyramid_unet_w32_1200_20260701/train_receipt.json` | `7928f79c038d8356d92d6f011ac4e9fe37cfad975a744a8450120dd1cccb0d23` |
| Premium still-SR pyramid noise-floor X2D U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_noisefloor_pyramid_unet_w32_1200_20260701/index.html` | `770863934dc20d00da2f0b1c1ed22b3826bf9ea56eb8bac41291f36cd1df69fb` |
| Premium still-SR pyramid noise-floor X2D U-Net panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_noisefloor_pyramid_unet_w32_1200_20260701/panel_sheet.jpg` | `e234f56f3dbc5fd1e9c6ccfa40fc2cc114233c0bc5b3bccda79742dabafdd87d` |
| Premium still-SR high-energy weighted X2D U-Net checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_energyweighted_noisefloor_unet_w32_1200_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_energyweighted_noisefloor_unet_w32_1200.pt` | `4661627805fce61492c034c5a95309b899f491e648c93d9962fcf21814ebb9dd` |
| Premium still-SR high-energy weighted X2D U-Net receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_energyweighted_noisefloor_unet_w32_1200_20260701/train_receipt.json` | `cdaa111814996fb2aca56e89971d084d2409c3fd078024ebfb245b15c00e3b03` |
| Premium still-SR high-energy weighted X2D U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_energyweighted_noisefloor_unet_w32_1200_20260701/index.html` | `f6ce75b7c622bf383e4aff130740801bfac41b7f65a9f5d3d7e963702b18bf61` |
| Premium still-SR high-energy weighted X2D U-Net panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_energyweighted_noisefloor_unet_w32_1200_20260701/panel_sheet.jpg` | `9a1d51fd43df294ca9f3ac1426959803f06ccc9eff8c3a0ac3a25346292c48e1` |
| Premium still-SR inverse-energy weighted X2D U-Net checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_energyinverse_noisefloor_unet_w32_1200_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_energyinverse_noisefloor_unet_w32_1200.pt` | `1c5d602dff09450998c2939b74077fbf6902f92a6e52a6a3ea30f0afab9d2617` |
| Premium still-SR inverse-energy weighted X2D U-Net receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_energyinverse_noisefloor_unet_w32_1200_20260701/train_receipt.json` | `94bd2ed056fcc66746202d82f84d27abe58dd2864afd45405932270383e3eb4f` |
| Premium still-SR inverse-energy weighted X2D U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_energyinverse_noisefloor_unet_w32_1200_20260701/index.html` | `3a1fa326b7a6f561d88dae6427e6025b8a737effd611deeadd03f0bed3fa1480` |
| Premium still-SR inverse-energy weighted X2D U-Net panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_energyinverse_noisefloor_unet_w32_1200_20260701/panel_sheet.jpg` | `e5386e7e394cf38ebdabb2ee31d52f85c33c585746e6a2a6d66fa59e2ac7f1a5` |
| Premium still-SR Fourier/band-loss X2D U-Net checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_fourierband_noisefloor_unet_w32_1200_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_fourierband_noisefloor_unet_w32_1200.pt` | `7dd7668e223cb99fe49156c5f4262f10da007793d6171bb3fc74e3a1216f2851` |
| Premium still-SR Fourier/band-loss X2D U-Net receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_fourierband_noisefloor_unet_w32_1200_20260701/train_receipt.json` | `05a319df6b325256f644107c2e03aceb826d9f0eeddc96c1b73ec3613954cc77` |
| Premium still-SR Fourier/band-loss X2D U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_fourierband_noisefloor_unet_w32_1200_20260701/index.html` | `da3ba0ab303c922bc435c15aacf29cd9a0463bb745fb9922ae535f21dc0b3d40` |
| Premium still-SR Fourier/band-loss X2D U-Net panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_fourierband_noisefloor_unet_w32_1200_20260701/panel_sheet.jpg` | `4241239c30b97d7a117e5b005b5d47d17c2c538011a79b698c459d9acdd309bb` |
| Premium still-SR light Fourier/band-loss X2D U-Net checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_lightfourierband_noisefloor_unet_w32_1200_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_lightfourierband_noisefloor_unet_w32_1200.pt` | `47e469c3fe059d93c4cc21a540b84362fefb3399adde4a40be2205f395958667` |
| Premium still-SR light Fourier/band-loss X2D U-Net receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_lightfourierband_noisefloor_unet_w32_1200_20260701/train_receipt.json` | `e15aca0e8f2f9e03bf96b3c0308e16fb1da8871881a1574b1e593c3a94b29bd8` |
| Premium still-SR light Fourier/band-loss X2D U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_lightfourierband_noisefloor_unet_w32_1200_20260701/index.html` | `f94313eec307a026a777804dda9467e7d45c26cf17a7f40f6ce86f50dd0657de` |
| Premium still-SR light Fourier/band-loss X2D U-Net panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_lightfourierband_noisefloor_unet_w32_1200_20260701/panel_sheet.jpg` | `1bd89864cf3236a0fa2c7b6c704e21352444012a8c58d30456a450d8990877d1` |
| Premium still-SR candidate-HF scaled X2D U-Net checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_candhfscale_noisefloor_unet_w32_1200_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_candhfscale_noisefloor_unet_w32_1200.pt` | `c2cefae212949853c86b4fd9ec67dfe2b0d82ccab01206039008881159136f30` |
| Premium still-SR candidate-HF scaled X2D U-Net receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_candhfscale_noisefloor_unet_w32_1200_20260701/train_receipt.json` | `e733df0b3d3288e6742582e448fd103c16f76d167cb842a8d54a43c14a558561` |
| Premium still-SR candidate-HF scaled X2D U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_candhfscale_noisefloor_unet_w32_1200_20260701/index.html` | `bc2295359b68f50fa2e4b4f4602edd7ad9a308265daa2213bb6b87e4a4a7a882` |
| Premium still-SR candidate-HF scaled X2D U-Net panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_candhfscale_noisefloor_unet_w32_1200_20260701/panel_sheet.jpg` | `dcd1af89863aee65fd44b709454b3fa977ef2e994a8f52dcf8c112d9e8f76077` |
| Premium still-SR half candidate-HF scaled X2D U-Net checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_candhfscale0p5_noisefloor_unet_w32_1200_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_candhfscale0p5_noisefloor_unet_w32_1200.pt` | `f67b0d82d18db716371ab83da375430f3bb1c435bd7d33a8928b52de081183b1` |
| Premium still-SR half candidate-HF scaled X2D U-Net receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_candhfscale0p5_noisefloor_unet_w32_1200_20260701/train_receipt.json` | `5ae9a7e5e2726792207a4806ea6f1e14cba968ac3de20c3461b62b1cbf6a3598` |
| Premium still-SR half candidate-HF scaled X2D U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_candhfscale0p5_noisefloor_unet_w32_1200_20260701/index.html` | `c017343ff6cb71d69cdcf7867031022f323a48581b3bfd959442ee2d252833d3` |
| Premium still-SR half candidate-HF scaled X2D U-Net panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_candhfscale0p5_noisefloor_unet_w32_1200_20260701/panel_sheet.jpg` | `a0dd5b8ed09cc78e56a7ddf31b8abfa3417ba0852a73868e60852b93e7c8474d` |
| Premium still-SR source-HF X2D U-Net checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_sourcehf_noisefloor_unet_w32_1200_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_sourcehf_noisefloor_unet_w32_1200.pt` | `481c44349242420071913d8701a69f8974dd2ce05222a3e9ae79d48274ce532f` |
| Premium still-SR source-HF X2D U-Net receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_sourcehf_noisefloor_unet_w32_1200_20260701/train_receipt.json` | `4021f5350b71ce03b1810123440a5f792cb447c7361d994b1ab271ba306475d7` |
| Premium still-SR source-HF X2D U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_sourcehf_noisefloor_unet_w32_1200_20260701/index.html` | `d9c97e0214ce253d4a6c37f18af89ed9626a42020cd66d346f6ae9084d795045` |
| Premium still-SR source-HF X2D U-Net panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_sourcehf_noisefloor_unet_w32_1200_20260701/panel_sheet.jpg` | `e77d6a48e1d2927900195450af7732e7842699c64cddb60f7317ad68ca72947c` |
| Premium still-SR source-HF stored-HF X2D U-Net checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_sourcehf_storedhf_noisefloor_unet_w32_1200_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_sourcehf_storedhf_noisefloor_unet_w32_1200.pt` | `e56ffd8303e0ec31ba61626746bc26c8ad5a69bbcbad32cec88a60676c1a961d` |
| Premium still-SR source-HF stored-HF X2D U-Net receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_sourcehf_storedhf_noisefloor_unet_w32_1200_20260701/train_receipt.json` | `86616d6ccb0830c25bb4f4c254c69a25a5b5379bc861808bc791685d5fdd02c0` |
| Premium still-SR source-HF stored-HF X2D U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_sourcehf_storedhf_noisefloor_unet_w32_1200_20260701/index.html` | `6ea9b8a89dc6d77634201f0a652aace3c847e37bb1b350becc663fc798e0fe78` |
| Premium still-SR source-HF stored-HF X2D U-Net panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_sourcehf_storedhf_noisefloor_unet_w32_1200_20260701/panel_sheet.jpg` | `a631e6eca9e1c410a010f272b782ffc9be063e8dce7320db4c7a9c1107e6bd8c` |
| Premium still-SR frame-context noise-floor X2D U-Net checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_framectx_noisefloor_unet_w32_1200_20260701/premium_still_sr_raw_cfa_residual_x2dsceneholdout_framectx_noisefloor_unet_w32_1200.pt` | `708d64355aacd297ef0d21cd4117cc6f1a0f342634466b25c6e3e40340b8ca6d` |
| Premium still-SR frame-context noise-floor X2D U-Net receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_framectx_noisefloor_unet_w32_1200_20260701/train_receipt.json` | `6e865ea47f4246cf893bcf1d932da9c9f4489c5a51e7e84092e4b26da1daad02` |
| Premium still-SR frame-context noise-floor X2D U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_framectx_noisefloor_unet_w32_1200_20260701/index.html` | `0dc2c53a82f21aca679286a2011148366f7d5cac0b49c94d9116949a531e0a69` |
| Premium still-SR frame-context noise-floor X2D U-Net panel | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_framectx_noisefloor_unet_w32_1200_20260701/panel_sheet.jpg` | `a9d3501339232cfc2b02da86f0c9401540dc28c0d3b9b4bda863cf90ed767c2f` |
| Premium still-SR raw-CFA residual X2D camera-balanced sampler receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_camera_balanced_w48_2200_20260630/train_receipt.json` | `5b1857af9e32b1554c1e4c69ba1fca9cade8490213775538d1360e29ca0fafdd` |
| Premium still-SR raw-CFA residual X2D context-padding receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_contextpad32_w48_1200_20260630/train_receipt.json` | `ec12cfa610c02ba2189ffcbff60820d494e653bc944af11d9e0fd4fbe335397f` |
| Premium still-SR raw-CFA residual X2D U-Net probe receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_unet_w32_1200_20260630/train_receipt.json` | `32a9d283678dcc9367d323ce83fecc98f7beab4d1d8e3c28e7d1b602d59170fe` |
| Premium still-SR raw-CFA residual X2D early-selection U-Net probe receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_unet_w32_1200_earlyselect_20260701/train_receipt.json` | `3fbab21edc548097d0cf452324aa014545348107822c8e30ba0ccb363951468d` |
| Premium still-SR raw-CFA residual X2D early-selection U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_unet_w32_1200_earlyselect_20260701/index.html` | `b1f74e5f09993b76ac3df6de4b096330e1bcfc7f21d92912d42372f17f1d4963` |
| Premium still-SR raw-CFA residual X2D frame-context U-Net probe receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_framectx_unet_w32_1200_20260630/train_receipt.json` | `60e260db6084e0a8499086c7633ef6af4855949e2b2948906f5f66b3efe062c8` |
| Premium still-SR raw-CFA residual Z8 frame-context U-Net probe receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_z8holdout_framectx_unet_w32_1200_20260630/train_receipt.json` | `acf9814a6fce227eaac2b394f15a52d454f0e4fe4e9d13de3bd4ce9310acbcbd` |
| Premium still-SR raw-CFA residual X2D full-crop U-Net probe receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2d1742_fullcrop_unet_w16_160_20260630/train_receipt.json` | `91fe43b4ec74010b44ce1b321f53dd88effe52c898acac8dc734feee7b2bc610` |
| Premium still-SR raw-CFA residual X2D full-crop stored-HF/context U-Net probe receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2d1742_fullcrop_contextstoredhf_unet_w24_360_20260630/train_receipt.json` | `1c00dc34c3e31479dc71192c4fbb216b8c7e453acb276d855ab882766c23f815` |
| Premium still-SR raw-CFA residual X2D full-crop spectral U-Net probe receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2d1742_fullcrop_spectral_unet_w24_420_20260630/train_receipt.json` | `64e8101e98b7e5b61b36b3ce6225d4f3f5ba8ac0c6761f093efeba109b0277ae` |
| Premium still-SR raw-CFA residual X2D global-context U-Net probe receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_globalctx_unet_w24_500_20260630/train_receipt.json` | `c751d496d52f2f33397594db72c132c1cec0e9c5c8beff83142b608631d6477d` |
| Premium still-SR raw-CFA residual X2D global-context U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_globalctx_unet_w24_500_20260630/index.html` | `fb54a9db8b6984d75afcc5668b0e3b207e198aae29eeddbe6bc1d490e9035bda` |
| Premium still-SR raw-CFA residual X2D masked-context global-context U-Net probe receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_maskedctx_globalctx_w24_420_20260630/train_receipt.json` | `cd3ce4422cee22d63c8d830b8ef871af008b9dd02f53222723d42a99f3cd2145` |
| Premium still-SR raw-CFA residual X2D masked-context global-context U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_maskedctx_globalctx_w24_420_20260630/index.html` | `f5f93f60bcdbeb40d276fc51be3c2ca39864f55db4f7da0a6b7195fe78748434` |
| Premium still-SR raw-target SNR audit JSON | `artifacts/premium_still_sr_raw_target_snr_audit_20260701/raw_target_snr_audit.json` | `28c76c799e14bd6c83ca312946731b3ab7bdb0ea41fb0956bd1107d7ca308cc7` |
| Premium still-SR raw-target SNR audit dashboard | `artifacts/premium_still_sr_raw_target_snr_audit_20260701/index.html` | `7e267673e68896a6d3999f17d03ef8e9ea2e3be52f54c668a70c93080e59f141` |
| Premium still-SR target distribution audit JSON | `artifacts/premium_still_sr_target_distribution_audit_20260701/target_distribution_audit.json` | `4defd67c6250b36946bf2a3aa0ae0617f98705fae46193f9a723d14d2127da43` |
| Premium still-SR target distribution audit dashboard | `artifacts/premium_still_sr_target_distribution_audit_20260701/index.html` | `abee7e5ef47b2c687ec97bac861d3de001f7065424653bdd13c47793c3aacc4c` |
| Premium still-SR next-experiment contract JSON | `artifacts/premium_still_sr_next_experiment_contract_transformer_teacher_20260701/premium_still_sr_next_experiment_contract.json` | `0d54ae8987ba8278fa385aff4dfb3d3b8fce9ec29e43dd772853b468daf08e37` |
| Premium still-SR next-experiment contract dashboard | `artifacts/premium_still_sr_next_experiment_contract_transformer_teacher_20260701/index.html` | `41e60a8c0f4bc31b871191416257b1ad7068a8725ac1cb9d5e9b0a8a9d90c9c5` |
| Premium still-SR window-attention teacher smoke checkpoint | `artifacts/premium_still_sr_raw_cfa_residual_model_dedup_window_attention_teacher_smoke_20260701/premium_still_sr_raw_cfa_residual.pt` | `c6b170d8ecdd5abc74697d110a29de1b71d20dab9334f341e043890bd93dbeac` |
| Premium still-SR window-attention teacher smoke receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_dedup_window_attention_teacher_smoke_20260701/train_receipt.json` | `6b86bed1e20b0638c51878a99b2d6ff4757b167ca989c6000fee8c25cdc5b538` |
| Premium still-SR window-attention teacher smoke dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_dedup_window_attention_teacher_smoke_20260701/index.html` | `ade2122b53540f437c863b2071e041430767a454a476d461a505dac1833e2ecf` |
| Premium still-SR window-attention teacher smoke panel | `artifacts/premium_still_sr_raw_cfa_residual_model_dedup_window_attention_teacher_smoke_20260701/panel_sheet.jpg` | `11111fb23c4d0264e1359ae7aaee368cf3011e630a501b0f6d2b3149c93aabcb` |
| Premium still-SR window-attention overlap eval smoke checkpoint | `artifacts/premium_still_sr_window_attention_overlap_eval_smoke_20260701/premium_still_sr_raw_cfa_residual.pt` | `150a5b3e9c9e5ed798e138740c303613f3327936df6b7de3a81d57b457815646` |
| Premium still-SR window-attention overlap eval smoke receipt | `artifacts/premium_still_sr_window_attention_overlap_eval_smoke_20260701/train_receipt.json` | `da2a5552378023d74efd71199257bc742d027b34aa67655da77ee7ee9cf68956` |
| Premium still-SR window-attention overlap eval smoke dashboard | `artifacts/premium_still_sr_window_attention_overlap_eval_smoke_20260701/index.html` | `c91e901c3f0ffd4961f55e9b17cdccd61b296170e66b57c8993ea5b35f38381a` |
| Premium still-SR window-attention overlap eval smoke panel | `artifacts/premium_still_sr_window_attention_overlap_eval_smoke_20260701/panel_sheet.jpg` | `746ab76ed560a1a835dc0b340819b5dcc15f17fa316358e81aace8900f2c1ba0` |
| Premium still-SR X2D PSF noise-floor U-Net probe receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_psf_noisefloor_unet_w32_1200_20260701/train_receipt.json` | `8dfad2a8ebd086af783ff0c03e6d1d54baac9afec79356ceb93904fc44eebe1e` |
| Premium still-SR X2D PSF noise-floor U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_psf_noisefloor_unet_w32_1200_20260701/index.html` | `74cef306d2a022aaba3ae159aa84513ff80a3065eb1bed2ef0d940797cf49a3d` |
| Premium still-SR X2D full-crop raw-context PSF U-Net probe receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_fullcrop_rawcontext_psf_unet_w32_900_20260701/train_receipt.json` | `8329f52f998cbeb8eeb47c975fb7356e1315e9ddff7a7c1dc61c5bd702889d35` |
| Premium still-SR X2D full-crop raw-context PSF U-Net dashboard | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_fullcrop_rawcontext_psf_unet_w32_900_20260701/index.html` | `904402cc144a3e0dc84363070744f8219583a3188007843942286fec18191c1d` |
| Premium still-SR PSF metadata gap JSON | `artifacts/premium_still_sr_psf_metadata_gap_20260701/premium_still_sr_psf_metadata_gap.json` | `3e2e8e049db9783c9bcbc5d313f7ee63fe186d3204054f2f4212674ad3dd7762` |
| Premium still-SR PSF metadata gap dashboard | `artifacts/premium_still_sr_psf_metadata_gap_20260701/index.html` | `3172dd6e11969ece44e76f547063c9dd480a6473dc59b77316c8f07a851f3308` |
| Premium still-SR PSF sidecar contract JSON | `artifacts/premium_still_sr_psf_sidecar_contract_20260701/premium_still_sr_psf_sidecar_contract.json` | `7ad7c2909a20a6a61d1c580f8505422bca4d5ab43c7a08ddb6ddcdc42a2125e5` |
| Premium still-SR PSF sidecar JSON | `artifacts/premium_still_sr_psf_sidecar_contract_20260701/premium_still_sr_psf_sidecar.json` | `9107805241edf9f976d7fe05bdc201f7c710b0d2d7cfc6668b26030e21334a7b` |
| Premium still-SR PSF sidecar dashboard | `artifacts/premium_still_sr_psf_sidecar_contract_20260701/index.html` | `3f91c82e99157fcb6a4bb65cedee1e0c6246ea427e074cc6d6d9413a76b05a33` |
| Premium still-SR X2D combined stored-HF/context probe receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_contextstoredhf_w40_1800_20260630/train_receipt.json` | `bb060baaedb3f2439eb3d51fd45002eb67278c87d276d403d208351946463ea7` |
| Premium still-SR X2D multiscale band-loss probe receipt | `artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_bandloss_w40_1800_20260630/train_receipt.json` | `0dd675d612e66461cea1d658fb62f91fe258703473aaa810d0c573f1fc18cb66` |

## Raw-Video PSF Gap Artifacts

These rows are diagnostic, not production promotion receipts. They preserve the
native Mission 1 PSF state for optional future PSF-conditioned video/SR work.

| artifact | path | sha256 |
|---|---|---|
| Mission 1 native PSF kernel-stability audit JSON | `artifacts/mission1_native_psf_kernel_stability_audit_20260630/kernel_stability_audit.json` | `e0814ab5b18767fd14307bf5ebce0016855da42ff99973782410ae171fc197f7` |
| Mission 1 native PSF kernel-stability audit dashboard | `artifacts/mission1_native_psf_kernel_stability_audit_20260630/index.html` | `a78d92485b905b8b61058b5f5dee0e916d1be977486c3ebaae95c06004c888ae` |
| Raw-video SR candidate scoreboard JSON | `artifacts/raw_video_sr_candidate_scoreboard_20260701/scoreboard.json` | `2b07eb4c68c09e71c273b336e5503aaf82a70c2f6059ec50ac98099a41bf1f48` |
| Raw-video SR candidate scoreboard dashboard | `artifacts/raw_video_sr_candidate_scoreboard_20260701/index.html` | `d3cc60b9f4732c0169b5967bf33f7ccc583471129a4b8bb9338183e7d7c3ca79` |
| Raw-video PSF detail metric decision receipt | `artifacts/current_goal_sr_psf_detail_metric_rerun_20260701/psf_detail_metric_decision.json` | `91d1ff935547bf7db3c8f5abc657d01d02bfb08ff7e09e45cf0253184d5c010a` |
| Raw-video PSF-detail-aware SR candidate scoreboard JSON | `artifacts/raw_video_sr_candidate_scoreboard_psf_detail_20260701/scoreboard.json` | `c7d38374df40e04934f729b31bf9bc5165f6556de92a7bcb338444dd83b8e0bf` |
| Raw-video PSF-detail-aware SR candidate scoreboard dashboard | `artifacts/raw_video_sr_candidate_scoreboard_psf_detail_20260701/index.html` | `65eede3af2d4e0f32ea2a125bee32eb4262ac8e34cc1fa3ce38a2ec11d4f37fd` |
| Raw-video PSF gradient/detail blocker audit JSON | `artifacts/raw_video_psf_gradient_detail_blocker_audit_20260701/gradient_detail_blocker_audit.json` | `6b302bc47a28954c5006a2c9604b5cc8a65b7280cb5bdeb89a6d961e4ac426e4` |
| Raw-video PSF gradient/detail blocker audit dashboard | `artifacts/raw_video_psf_gradient_detail_blocker_audit_20260701/index.html` | `e08440b7417225d7970c2820b00c824506dde4027a68ed89999ab9e3cbd99e18` |
| Raw-video PSF detail metric audit JSON | `artifacts/raw_video_psf_detail_metric_audit_20260701/raw_video_psf_detail_metric_audit.json` | `6b6e35dadebd6670c9dda1cd1051eae81d9945f1d9631d34f92d3c564716b23e` |
| Raw-video PSF detail metric audit dashboard | `artifacts/raw_video_psf_detail_metric_audit_20260701/index.html` | `7066640f6c4b5e332d18a25afb7529ef671c76c2c92a24a49f91d3fb45ec5d8a` |
| Raw-video PSF detail metric rerun Mission42 baseline summary | `artifacts/raw_video_psf_detail_metrics_fullframe_rerun_20260701/mission42_baseline_fullframe/summary.json` | `4e9dddacac10bf02f1a190da6e10dad45dd9770fa8d507e406e7a13557aa3af1` |
| Raw-video PSF detail metric rerun Mission42 candidate summary | `artifacts/raw_video_psf_detail_metrics_fullframe_rerun_20260701/mission42_candidate_fullframe/summary.json` | `03bdf41edde228419645dbc8b24948bde07ccd51b5dc8c035b615cd0914bd96b` |
| Raw-video PSF detail metric rerun Z8 baseline summary | `artifacts/raw_video_psf_detail_metrics_fullframe_rerun_20260701/z8_baseline_fullframe/summary.json` | `080cba9d8f1a3ae4eaacf8e1691e1e9e93bfa8c764c69162afce8ada1604c236` |
| Raw-video PSF detail metric rerun Z8 candidate summary | `artifacts/raw_video_psf_detail_metrics_fullframe_rerun_20260701/z8_candidate_fullframe/summary.json` | `6f2fb7b4709bfb92870509b11b7fde12af85c8eb4882584f96f384001b947eff` |
| Raw-video PSF detail metric rerun audit JSON | `artifacts/raw_video_psf_detail_metric_audit_rerun_20260701/raw_video_psf_detail_metric_audit.json` | `28f2a16537b23c1d2364cad215ac7e9fcc531774bd7fc8c91153d512420e8866` |
| Raw-video PSF detail metric rerun audit dashboard | `artifacts/raw_video_psf_detail_metric_audit_rerun_20260701/index.html` | `fe383c40ae7477e0cb47dea5cfe60c8a6cf936381437dd614ed95dea9eaba56e` |
| Bayer resize PSF known-kernel validation JSON | `artifacts/bayer_resize_psf_known_kernel_validation_20260701/known_kernel_validation.json` | `381f9597a6add3fd9ca4d9e7880b36d1065926f1e6985b0fdd1b5155625f6f13` |
| Bayer resize PSF known-kernel validation receipt | `artifacts/bayer_resize_psf_known_kernel_validation_20260701/bayer_resize_psf_receipt.json` | `b5d6bfdda52c2b66620a0f229d1443aabc0a3e39d1da1589a8f797ac61894c70` |
| Bayer resize PSF known-kernel validation dashboard | `artifacts/bayer_resize_psf_known_kernel_validation_20260701/index.html` | `4c32f1a320ae245cc1b5235eceab8475bccdbdc315f1e37164decafb7f6a3d1a` |
| Raw-video PSF next-experiment contract JSON | `artifacts/raw_video_psf_next_experiment_contract_20260701/raw_video_psf_next_experiment_contract.json` | `df23e0f05f9829a99edb15c24c326ff18dd1da4e42c112f112049356da027996` |
| Raw-video PSF next-experiment contract dashboard | `artifacts/raw_video_psf_next_experiment_contract_20260701/index.html` | `ab25ef25dc61ad2e1eeb33c8cdeab0df8acde4625e5c4964bff8d9858276a470` |

Install the portable model-root artifacts as:

```bash
$GPR_MODEL_ROOT/
  BayInBayOut_1x_AAon_w16_ANE_gpr_tools_q3.pt
  BayInBayOut_1x_AAon_w16_ANE_ML2_q3.pt
  BayInBayOut_2x_AAon_w16_ANE_ML2_q3_dec2_diverse.pt
```

The verifier also checks a repo-local `models/` directory for developer
overrides, but production setup should use `GPR_MODEL_ROOT`.

## Verify

Inventory mode, suitable for CI:

```bash
python3 tools/verify_production_artifacts.py
python3 tests/quality_gates/check_registry_consistency.py
```

Release mode:

```bash
python3 tools/verify_production_artifacts.py --strict
python3 tests/quality_gates/check_registry_consistency.py --strict-artifacts
python3 tests/quality_gates/audit_ship_pipelines.py --strict
python3 tests/quality_gates/audit_production_readiness.py --strict
python3 tools/mission1_numbered_list_readiness.py --external-root /Volumes/OWC_8TB/gpr_work --require-production
```

`audit_ship_pipelines.py` is the narrow committed-run check for registry roles
tagged `ship-*`. `audit_production_readiness.py --strict` is the broader
release checklist: stills, video quality, PREVIEW/non-REF receipts, noise/signal
guards, UPRESABLE, `.gvid`, MOV compatibility, Pi 5 / Mission 1 setup, and
platform speed receipts. `tools/test/check_release_evidence_manifest.py`
validates the compact release manifest at
`docs/release_evidence_manifest.json`.
`mission1_numbered_list_readiness.py --require-production` is the final
numbered-list promotion gate; it must remain blocked until actual Mission 1
camera handoff and actual camera preview UI handoff receipts are present.

The current offline/review PREVIEW production path is
`preview_q8_threeway_runtime_fullframe_v1`. It is a no-REF, full-frame q8
three-way runtime route with an external receipt under
`artifacts/preview_runtime_policy_20260613/q8_threeway_runtime_full_holdout_v1/`.
That receipt reports 84/84 rows passing on the 28-image holdout, weighted
runtime of 13.65 seconds per image, 0.073 fps, and 5.37 GB peak RSS. It is not
the live/camera-back path; live PREVIEW remains a separate speed/quality
problem documented in `docs/VIDEO_STATUS.md`.

## Runtime resolution

Registry checkpoint paths are portable relative paths such as
`models/name.pt`. Runtime tools resolve them in this order:

1. absolute path, if the registry entry is absolute;
2. repo-local path, for developer overrides;
3. `GPR_MODEL_ROOT` and `GPR_CHECKPOINT_ROOT`;
4. `GPR_EXTERNAL_ROOT/models` and `GPR_EXTERNAL_ROOT/checkpoints`;
5. `/Volumes/OWC_8TB/gpr_work/models` and `/Volumes/OWC_8TB/gpr_work/checkpoints`.

Missing artifacts are warnings in inventory mode and hard failures in strict
release mode.

## What stays off main

- `.pt`, `.pth`, `.mlpackage`, and intermediate training checkpoints;
- full dashboards with generated image/video payloads;
- ProRes/MOV/GVID review outputs;
- large training tiles and corpus extracts.

Commit only the registry hash, training sidecar summary, quality-gate receipt,
and compact documentation needed to reproduce the artifact.

## Registry Review Artifacts

These rows are required by the release evidence manifest guard for temporary
registry-review candidates that are not final ship artifacts.

| artifact | path | sha256 |
|---|---|---|
| Mission+Z8 q4/t2 coord-detail alpha0p5 SR registry checkpoint (`mission1_native12_8k_sr_q4t2_coord_detail_alpha0p5_v1` `ckpt_path`) | `artifacts/current_goal_cnn_hardtile_gate_aligned_20260624/interp_step1_to_balanced_step200/q4t2_coord_detail_balanced_step001_to_step200_alpha0p5.pt` | `791628778f74b13542677edeb5de7934b88d274531a8ec1755d8cf3d6388fb07` |
| Mission+Z8 q4/t2 coord-detail alpha0p5 SR training pairs (`mission1_native12_8k_sr_q4t2_coord_detail_alpha0p5_v1` `training_pairs_path`) | `artifacts/current_goal_cnn_hardtile_gate_aligned_20260624/mission42_z8all24_q4t2_plus_targetdetail_hardtiles_w96.npz` | `59aa38bac909e8221f48de2b20e9b00d2cc4cc3f6cf24d143bf4cba08e387205` |
| Mission+Z8 q4/t2 coord-detail PSF-focus step-75 SR registry-review checkpoint (`mission1_native12_8k_sr_coord_detail_psf_focus_step0075_v1` `ckpt_path`) | `artifacts/current_goal_sr_coord_detail_context_20260701/eval_checkpoints/coord_detail_from_psf_focus_s150_step000075.pt` | `9e3e57ec5555bc8387809eb3bd76003bd0422b37a99d8db3a8a4d12b18a7ae46` |
| Mission+Z8 q4/t2 coord-detail PSF-focus step-75 SR training pairs (`mission1_native12_8k_sr_coord_detail_psf_focus_step0075_v1` `training_pairs_path`) | `artifacts/current_goal_sr_psf_gradient_focus_20260701/mission42_z8_all24_q4t2_inputs_w96_repaired_lowclean.npz` | `52d7e97a7a2e17e758e5d255db6ce6cc9207fd1cdd75af849a9cf7205873259e` |
| Mission+Z8 q4/t2 coord-detail PSF-focus step-75 `.gvid` decode-to-SR receipt (`mission1_native12_8k_sr_coord_detail_psf_focus_step0075_v1` `gvid_decode_sr_multiframe_receipt`) | `artifacts/mission1_native12_gvid_to_8k_sr_coord_detail_psf_focus_step0075_multiframe_20260701/receipt.json` | `fc4b0f2eb584ed70547defec9b5120b683f212cb67b50d26c5c383d148559850` |
| Mission+Z8 q4/t2 coord-detail PSF-focus step-75 editable packaging receipt (`mission1_native12_8k_sr_coord_detail_psf_focus_step0075_v1` `gvid_decode_sr_packaging_receipt`) | `artifacts/mission1_native12_gvid_to_8k_sr_coord_detail_psf_focus_step0075_packaging_q3_20260701/packaging_receipt.json` | `2de4910ac458862da7f75154dd732488073dbd13e4a40c4735fa531d94b3d606` |
| Mission+Z8 q4/t2 coord-detail PSF-focus step-75 Mission metadata transplant audit (`mission1_native12_8k_sr_coord_detail_psf_focus_step0075_v1` `mission_metadata_transplant_audit`) | `artifacts/mission1_native12_gvid_to_8k_sr_coord_detail_psf_focus_step0075_metadata_transplant_20260701/metadata_transplant_audit.json` | `33ba940fe5276f456be49f291fd3de104b7fc46f635a5141d15ae7802edf7d10` |
