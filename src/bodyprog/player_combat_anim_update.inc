        s16 ssp20;
        s16 temp_a1;
        s32 keyframeIdx0;
        s32 keyframeIdx1;
        u8  weaponAttack;

        weaponAttack = g_SysWork.playerCombat.weaponAttack;

        switch (g_SysWork.playerCombat.weaponAttack)
        {
            case WEAPON_ATTACK(EquippedWeaponId_KitchenKnife, AttackInputType_Tap):
                keyframeIdx0 = 619;
                keyframeIdx1 = 613;
                break;

            case WEAPON_ATTACK(EquippedWeaponId_Chainsaw, AttackInputType_Tap):
                keyframeIdx0 = 630;
                keyframeIdx1 = 624;
                break;

            case WEAPON_ATTACK(EquippedWeaponId_RockDrill, AttackInputType_Tap):
                keyframeIdx0 = 568;
                keyframeIdx1 = 568;
                break;

            case WEAPON_ATTACK(EquippedWeaponId_Axe, AttackInputType_Tap):
                keyframeIdx0 = 625;
                keyframeIdx1 = 618;
                break;

            case WEAPON_ATTACK(EquippedWeaponId_SteelPipe, AttackInputType_Tap):
            case WEAPON_ATTACK(EquippedWeaponId_Hammer,    AttackInputType_Tap):
                keyframeIdx0 = 648;
                keyframeIdx1 = 642;
                break;

            case WEAPON_ATTACK(EquippedWeaponId_Katana, AttackInputType_Tap):
                keyframeIdx0 = 619;
                keyframeIdx1 = 612;
                break;

            default:
                keyframeIdx1 = 0;
                keyframeIdx0 = 0;
                break;
        }

        if (g_SysWork.playerWork.extra.state == PlayerState_Combat)
        {
            playerProps.field_104 += g_DeltaTime;

            if (!g_GameWork.config.extraWeaponCtrl)
            {
                g_Player_HasActionInput      = false;
                g_Player_HasMoveInput        = false;
                g_Player_IsShooting          = false;
                g_Player_IsAttacking         = false;
                g_Player_IsHoldAttack        = false;
                g_Player_IsAiming            = false;
                g_Player_IsRunning           = false;
                g_Player_IsMovingBackward    = false;
                g_Player_IsMovingForward     = false;
                g_Player_IsSteppingRightTap  = false;
                g_Player_IsSteppingRightHold = false;
                g_Player_IsTurningRight      = false;
                g_Player_IsSteppingLeftTap   = false;
                g_Player_IsSteppingLeftHold  = false;
                g_Player_IsTurningLeft       = false;
            }
        }

        // Attack type (except melee multitap) and animation.
        if (extra->model.controlState == 0)
        {
            g_Player_MeleeAttackType  = 0;
            g_Player_IsMultiTapAttack = 0;
#ifdef SH_PC_PORT
            /* Slash starting — consume the queued click that triggered it
             * so it doesn't also trigger the multi-tap. */
            if (s_pcMtClickQueue > 0) s_pcMtClickQueue--;
#endif

            playerProps.flags &= ~PlayerFlag_Shooting;
            playerProps.flags &= ~PlayerFlag_Unk6;

            if (g_SysWork.playerCombat.weaponAttack >= WEAPON_ATTACK(EquippedWeaponId_Handgun, AttackInputType_Tap))
            {
                g_Player_MeleeAttackType    = 0;
                g_Player_AttackAnimIdx = g_Player_EquippedWeaponInfo.animAttackHold;
                D_800AF220                  = g_Player_EquippedWeaponInfo.field_A >> 4;
            }
            else if (g_Player_IsAttacking && g_SysWork.playerCombat.weaponAttack != WEAPON_ATTACK(EquippedWeaponId_RockDrill, AttackInputType_Tap))
            {
                g_Player_MeleeAttackType = 1;
                g_Player_AttackAnimIdx   = g_Player_EquippedWeaponInfo.animAttackHold - 4;
                D_800AF220               = (g_Player_EquippedWeaponInfo.field_A >> 4) - 2;
            }
            else
            {
                g_Player_MeleeAttackType = 0;

                // Handle Rock Drill animation.
                if (g_SysWork.playerCombat.weaponAttack != WEAPON_ATTACK(EquippedWeaponId_RockDrill, AttackInputType_Tap) ||
                    g_Player_RockDrill_DirectionAttack == 0)
                {
                    g_Player_AttackAnimIdx = g_Player_EquippedWeaponInfo.animAttackHold;
                    D_800AF220             = g_Player_EquippedWeaponInfo.field_A >> 4;
                }
                else if (g_Player_RockDrill_DirectionAttack == NO_VALUE)
                {
                    g_Player_AttackAnimIdx = g_Player_EquippedWeaponInfo.animAttackHold + 4;
                    D_800AF220                  = (g_Player_EquippedWeaponInfo.field_A >> 4) + 2;
                }
                else
                {
                    g_Player_AttackAnimIdx = g_Player_EquippedWeaponInfo.animAttackHold + 2;
                    D_800AF220                  = (g_Player_EquippedWeaponInfo.field_A >> 4) + 1;
                }
            }

            extra->model.controlState++;

            if (g_SysWork.playerCombat.weaponAttack < WEAPON_ATTACK(EquippedWeaponId_Handgun, AttackInputType_Tap))
            {
                g_SysWork.playerCombat.weaponAttack = WEAPON_ATTACK(WEAPON_ATTACK_ID_GET(g_SysWork.playerCombat.weaponAttack), AttackInputType_Tap);
            }

            g_SysWork.playerCombat.weaponAttack += g_Player_MeleeAttackType * 10; // TODO: Macro for this?

            D_800C44D0 = HARRY_BASE_ANIM_INFOS[g_Player_AttackAnimIdx].startKeyframeIdx + D_800AD4C8[g_SysWork.playerCombat.weaponAttack].field_E;
            D_800C44D4 = HARRY_BASE_ANIM_INFOS[g_Player_AttackAnimIdx].startKeyframeIdx + D_800AD4C8[g_SysWork.playerCombat.weaponAttack].field_E +
                         D_800AD4C8[g_SysWork.playerCombat.weaponAttack].field_F;
#ifdef SH_PC_PORT
            /* Instant fire (free-aim): jump the recoil anim straight to the damage
             * window start so the bullet dispatches THIS frame (the keyframe check
             * at ~3752/3790 passes immediately), then the recoil plays out from the
             * shot. This is in the controlState==0 Attack-entry block, so it runs
             * once on the press — NOT every frame (which would stall recoil at the
             * damage frame). Ranged + OTS/TPS only; melee untouched. */
            if (g_DebugThirdPersonCam && D_800C44D0 > 0 &&
                g_SysWork.playerCombat.weaponAttack >= WEAPON_ATTACK(EquippedWeaponId_Handgun, AttackInputType_Tap))
            {
                extra->model.anim.keyframeIdx = D_800C44D0;
                extra->model.anim.time        = Q12((s32)D_800C44D0);
            }
#endif
        }

        // Used for make continuos/hold shooting smoother?
        if (g_SysWork.targetNpcIdx != NO_VALUE &&
            g_SysWork.playerCombat.weaponAttack >= WEAPON_ATTACK(EquippedWeaponId_Handgun, AttackInputType_Tap))
        {
            if (!g_GameWork.config.extraAutoAiming)
            {
                if (!(g_SysWork.field_2388.field_154.effectsInfo_0.field_0.s_field_0.field_0 & 1))
                {
                    func_8005CD38(&enemyAttackedIdx, &playerProps.field_122, &g_SysWork.playerCombat, 0x238, Q12(10.0f), 0);
                    func_8005D50C(&g_Player_TargetNpcIdx, &D_800C4554, &D_800C4556, &g_SysWork.playerCombat, enemyAttackedIdx, Q12_ANGLE(20.0f));
                }
                else
                {
                    func_8005CD38(&enemyAttackedIdx, &playerProps.field_122, &g_SysWork.playerCombat, 0x238, Q12(3.0f), 0);
                    func_8005D50C(&g_Player_TargetNpcIdx, &D_800C4554, &D_800C4556, &g_SysWork.playerCombat, enemyAttackedIdx, Q12_ANGLE(20.0f));
                }
            }
            else
            {
                enemyAttackedIdx = g_SysWork.targetNpcIdx;
            }

            if (enemyAttackedIdx == NO_VALUE && enemyAttackedIdx == g_Player_TargetNpcIdx)
            {
                D_800C4556 = NO_VALUE;
                D_800C4554 = NO_VALUE;
            }

            if (enemyAttackedIdx == g_SysWork.targetNpcIdx)
            {
                player->angleToTarget = Q12_FRACT(ratan2((g_SysWork.npcs[enemyAttackedIdx].position.vx + g_SysWork.npcs[enemyAttackedIdx].collision.shapeOffsets.box.vx) - g_SysWork.playerWork.player.position.vx,
                                                   (g_SysWork.npcs[enemyAttackedIdx].position.vz + g_SysWork.npcs[enemyAttackedIdx].collision.shapeOffsets.box.vz) - g_SysWork.playerWork.player.position.vz) +
                                            Q12_ANGLE(360.0f));
            }
            else
            {
                player->angleToTarget = player->rotation.vy;
            }

            if (extra->model.stateStep == 0
#ifdef SH_PC_PORT
                /* Only START a new shot while the fire button is actually held.
                 * This targeting branch dispatches off weaponAttack+targetNpcIdx
                 * alone, bypassing the fire gate's (IsAttacking||IsShooting)
                 * check at ~line 5232. Once locked + armed it would otherwise
                 * self-sustain — Harry keeps firing after the player releases C
                 * (the "fires without holding" latch). lowerBodyState is >= Aim
                 * during the Attack state, so IsShooting reflects the live button
                 * (see ~line 9726), making this a faithful release check. */
                && (g_Player_IsShooting || g_Player_IsAttacking)
#endif
               )
            {
                extra->model.anim.status = ANIM_STATUS(HarryAnim_Unk30, false);
                extra->model.stateStep++;
#ifdef SH_PC_PORT
                /* Targeting branch: same kf-carryover issue as the Unk11 path.
                 * Status is Unk30 BLEND (slot 60, startKf=NO_VALUE) so kf carries
                 * over from previous cycle's endKf=604, which both skips the
                 * damage window AND trips pcAttackDone on the dispatch frame.
                 * Reset kf to (active startKf − 1) = 593 so BlendLinear can
                 * transition to active first; next frame damage fires correctly. */
                if (extra->model.anim.status > 0 && extra->model.anim.status < 76)
                {
                    s16 pcFireStartKf = HARRY_BASE_ANIM_INFOS[extra->model.anim.status].startKeyframeIdx;
                    if (pcFireStartKf <= 0 && (extra->model.anim.status & 1) == 0)
                    {
                        u8 activeSt = (u8)(extra->model.anim.status | 1);
                        if (activeSt < 76)
                        {
                            s16 activeStartKf = HARRY_BASE_ANIM_INFOS[activeSt].startKeyframeIdx;
                            if (activeStartKf > 1) {
                                pcFireStartKf = activeStartKf - 1;
                            }
                        }
                    }
                    if (pcFireStartKf > 0)
                    {
                        extra->model.anim.keyframeIdx = pcFireStartKf;
                        extra->model.anim.time        = Q12((s32)pcFireStartKf);
                    }
                }
#endif
            }
        }
        else
        {
            if (g_SysWork.targetNpcIdx != NO_VALUE && !g_GameWork.config.extraAutoAiming)
            {
                if (!(g_SysWork.field_2388.field_154.effectsInfo_0.field_0.s_field_0.field_0 & (1 << 0)))
                {
                    func_8005CD38(&enemyAttackedIdx, &playerProps.field_122, &g_SysWork.playerCombat, Q12(3.0f), Q12(3.0f), 5);
                }
                else
                {
                    func_8005CD38(&enemyAttackedIdx, &playerProps.field_122, &g_SysWork.playerCombat, Q12(1.0f), Q12(1.0f), 5);
                }

                if (enemyAttackedIdx == g_SysWork.targetNpcIdx)
                {
                    temp_a1 = Q12_FRACT(ratan2((g_SysWork.npcs[enemyAttackedIdx].position.vx + g_SysWork.npcs[enemyAttackedIdx].collision.shapeOffsets.box.vx) - g_SysWork.playerWork.player.position.vx,
                                               (g_SysWork.npcs[enemyAttackedIdx].position.vz + g_SysWork.npcs[enemyAttackedIdx].collision.shapeOffsets.box.vz) - g_SysWork.playerWork.player.position.vz) + Q12(1.0f));

                    Math_ShortestAngleGet(player->rotation.vy, temp_a1, &ssp20);
                    D_800C454C = g_DeltaTime * 0xF;

                    if (ABS(ssp20) >= 0x80)
                    {
                        if (ssp20 < 0)
                        {
                            D_800C454C = -D_800C454C;
                        }
                    }
                    else
                    {
                        player->angleToTarget = player->rotation.vy = temp_a1;
                        D_800C454C             = 0;
                    }
                }
            }
            else
            {
                enemyAttackedIdx                                           = NO_VALUE;
                playerProps.field_122 = Q12_ANGLE(90.0f);
                player->angleToTarget                                            = player->rotation.vy;
            }

            if (g_SysWork.playerCombat.weaponAttack >= WEAPON_ATTACK(EquippedWeaponId_Handgun, AttackInputType_Tap))
            {
                if ((playerProps.flags & PlayerFlag_Unk11)
#ifdef SH_PC_PORT
                    /* TPS/OTS instant fire: Harry already holds the gun extended at
                     * the aim-hold (kf591), so route EVERY shot — including the first
                     * — through the short Unk30 recoil instead of the full Unk36
                     * (gun raise + extend + recoil). The bullet then dispatches as the
                     * recoil starts (kf ~593->594 damage window) instead of after the
                     * 12-frame raise windup — that windup is the "animation finishes
                     * before he fires" delay. The recoil anim itself still plays
                     * (unchanged); between-shots cadence is still its length. */
                    || g_DebugThirdPersonCam
#endif
                   )
                {
                    if (extra->model.stateStep == 0)
                    {
                        extra->model.anim.status = g_Player_EquippedWeaponInfo.animAttack - 12;
                        extra->model.stateStep++;
#ifdef SH_PC_PORT
                        /* Handgun Unk11 (follow-up) path: animAttack_7-12 is a
                         * BLEND phase (Unk30 false, slot 60) whose startKf is
                         * NO_VALUE. Without intervention kf carries over from
                         * the previous cycle's endKf=604, and that fails in
                         * two ways:
                         *   - kf=604 is PAST the damage window (594-599) → the
                         *     damage trigger on the dispatch frame never fires,
                         *   - kf=604 >= active endKf=604 → pcAttackDone fires
                         *     immediately, state→Aim, CombatAnimUpdate stops
                         *     running before BlendLinear can transition status
                         *     to active and the damage trigger can re-fire.
                         *
                         * Reset kf to (active startKf − 1), i.e. 593 for
                         * handgun. The dispatch frame then has:
                         *   - kf < 594 → damage trigger skipped (correct: still
                         *     in blend, status bit 0 = 0 anyway),
                         *   - kf < 604 → pcAttackDone skipped, controlState
                         *     advances normally,
                         *   - BlendLinear runs in the anim update and sets
                         *     kf=endKf=594 + status→active(61).
                         * Next CombatAnimUpdate frame: status=61 active, kf=594
                         * in damage window → damage fires, combat dispatcher
                         * keeps field_44.field_0=1, hit applies. */
                        if (extra->model.anim.status > 0 && extra->model.anim.status < 76)
                        {
                            s16 pcFireStartKf = HARRY_BASE_ANIM_INFOS[extra->model.anim.status].startKeyframeIdx;
                            if (pcFireStartKf <= 0 && (extra->model.anim.status & 1) == 0)
                            {
                                u8 activeSt = (u8)(extra->model.anim.status | 1);
                                if (activeSt < 76)
                                {
                                    s16 activeStartKf = HARRY_BASE_ANIM_INFOS[activeSt].startKeyframeIdx;
                                    if (activeStartKf > 1) {
                                        pcFireStartKf = activeStartKf - 1;
                                    }
                                }
                            }
                            if (pcFireStartKf > 0)
                            {
                                extra->model.anim.keyframeIdx = pcFireStartKf;
                                extra->model.anim.time        = Q12((s32)pcFireStartKf);
                            }
                        }
#endif
                    }
                }
                else
                {
                    if (extra->model.stateStep == 0)
                    {
                        extra->model.anim.status = g_Player_EquippedWeaponInfo.animAttack;
                        extra->model.stateStep++;
#ifdef SH_PC_PORT
                        if (extra->model.anim.status > 0 && extra->model.anim.status < 76)
                        {
                            s16 pcFireStartKf = HARRY_BASE_ANIM_INFOS[extra->model.anim.status].startKeyframeIdx;
                            if (pcFireStartKf <= 0 && (extra->model.anim.status & 1) == 0)
                            {
                                u8 activeSt = (u8)(extra->model.anim.status | 1);
                                if (activeSt < 76)
                                {
                                    pcFireStartKf = HARRY_BASE_ANIM_INFOS[activeSt].startKeyframeIdx;
                                }
                            }
                            if (pcFireStartKf > 0)
                            {
                                extra->model.anim.keyframeIdx = pcFireStartKf;
                                extra->model.anim.time        = Q12((s32)pcFireStartKf);
                            }
                        }
#endif
                    }
                }
            }
            else if (g_Player_IsAttacking && g_SysWork.playerCombat.weaponAttack != WEAPON_ATTACK(EquippedWeaponId_RockDrill, AttackInputType_Tap))
            {
                if (extra->model.stateStep == 0)
                {
#ifdef SH_PC_PORT
                    SH_DBG("[MELEE-SS0] SWIPE IsAttacking=%d weaponAttack=%d animIdx=%d",
                           (int)g_Player_IsAttacking, (int)g_SysWork.playerCombat.weaponAttack,
                           (int)(g_Player_EquippedWeaponInfo.animAttack - 4));
#endif
                    extra->model.anim.status = g_Player_EquippedWeaponInfo.animAttack - 4;
                    extra->model.stateStep++;
                }
            }
            else if (g_SysWork.playerCombat.weaponAttack != WEAPON_ATTACK(EquippedWeaponId_RockDrill, AttackInputType_Tap) ||
                     g_Player_RockDrill_DirectionAttack == 0)
            {
                if (extra->model.stateStep == 0)
                {
#ifdef SH_PC_PORT
                    SH_DBG("[MELEE-SS0] STAB IsAttacking=%d weaponAttack=%d animIdx=%d",
                           (int)g_Player_IsAttacking, (int)g_SysWork.playerCombat.weaponAttack,
                           (int)g_Player_EquippedWeaponInfo.animAttack);
#endif
                    extra->model.anim.status = g_Player_EquippedWeaponInfo.animAttack;
                    extra->model.stateStep++;
                }
            }
            else if (g_Player_RockDrill_DirectionAttack == NO_VALUE)
            {
                if (extra->model.stateStep == 0)
                {
                    extra->model.anim.status = g_Player_EquippedWeaponInfo.animAttack + 4;
                    extra->model.stateStep++;
                }
            }
            else
            {
                if (extra->model.stateStep == 0)
                {
                    extra->model.anim.status = g_Player_EquippedWeaponInfo.animAttack + 2;
                    extra->model.stateStep++;
                }
            }
        }

        // Audio effects for attack animations, no ammo audio and removes ammo value.
        // Additionally trigger some special state for the Rock Drill.
        if (g_SysWork.playerCombat.weaponAttack < WEAPON_ATTACK(EquippedWeaponId_Handgun, AttackInputType_Tap))
        {
            if (WEAPON_ATTACK_ID_GET(g_SysWork.playerCombat.weaponAttack) != WEAPON_ATTACK(EquippedWeaponId_Chainsaw,  AttackInputType_Tap) &&
                WEAPON_ATTACK_ID_GET(g_SysWork.playerCombat.weaponAttack) != WEAPON_ATTACK(EquippedWeaponId_RockDrill, AttackInputType_Tap))
            {
                if (extra->model.anim.keyframeIdx >= D_800C44D0 && D_800C44D4 >= extra->model.anim.keyframeIdx)
                {
                    if (!(playerProps.flags & PlayerFlag_Unk2))
                    {
                        player->field_44.field_0 = 1;

                        func_8005DC1C(g_Player_EquippedWeaponInfo.attackSfx, &player->position, Q8(0.5f), 0);

                        player->properties.player.field_10C                       = 0x40;
                        playerProps.flags |= PlayerFlag_Unk2;
                    }
                }
                else if (D_800C44D4 < extra->model.anim.keyframeIdx)
                {
                    playerProps.flags &= ~PlayerFlag_Unk2;
                }
            }
            else if (playerProps.gasWeaponPowerTimer == Q12(0.0f))
            {
                if (extra->model.anim.keyframeIdx >= D_800C44D0 && D_800C44D4 >= extra->model.anim.keyframeIdx &&
                    !(playerProps.flags & PlayerFlag_Unk2))
                {
                    player->field_44.field_0                                     = 1;
                    playerProps.flags |= PlayerFlag_Unk2;
                }
            }
            else
            {
                if (player->field_44.field_0 <= 0)
                {
                    player->field_44.field_0 = 1;
                }

                player->properties.player.field_10C = 0x40;
            }
        }
        else
        {
            if (extra->model.anim.keyframeIdx >= D_800C44D0 && D_800C44D4 >= extra->model.anim.keyframeIdx &&
                !(playerProps.flags & PlayerFlag_Shooting))
            {
                playerProps.flags |= PlayerFlag_Shooting;

                if (g_SysWork.playerCombat.currentWeaponAmmo != 0)
                {
                    player->field_44.field_0 = 1;

                    if (g_SysWork.playerCombat.weaponAttack != WEAPON_ATTACK(EquippedWeaponId_HyperBlaster, AttackInputType_Tap))
                    {
                        g_SysWork.playerCombat.currentWeaponAmmo--;
                        g_SavegamePtr->items[g_SysWork.playerCombat.weaponInventoryIdx].count_1--;

                        func_8005DC1C(g_Player_EquippedWeaponInfo.attackSfx, &player->position, Q8(0.5f), 0);
                    }
                    else
                    {
                        func_8005DC1C(g_Player_EquippedWeaponInfo.attackSfx, &player->position, Q8_CLAMPED(0.19f), 0);
                    }

                    player->properties.player.field_10C = 0xC8;
                }
                else
                {
                    func_8005DC1C(g_Player_EquippedWeaponInfo.outOfAmmoSfx, &player->position, Q8(0.5f), 0);

                    player->properties.player.field_10C = 32;
                    extra->model.anim.keyframeIdx  = D_800C44F0[D_800AF220].field_6 - 3;
                    extra->model.anim.time          = Q12(D_800C44F0[D_800AF220].field_6 - 3);

                    if (g_SysWork.playerWork.extra.lowerBodyState == PlayerLowerBodyState_Aim)
                    {
                        player->model.anim.keyframeIdx = D_800C44F0[D_800AF220].field_6 - 3;
                        player->model.anim.time         = Q12(D_800C44F0[D_800AF220].field_6 - 3);
                    }
                }
            }
        }

        // Finish attack animation.
        // Though more context about `D_800AF220` and `D_800C44F0` is required,
        // they likely indicate if an attack animation has finished.
#ifdef SH_PC_PORT
        // PC: detect "active fire/recoil anim has finished" using direction-aware end-of-anim. Forward (duration > 0) ends at endKeyframeIdx; backward (e.g. ready-pose Q12(-35)) ends at startKeyframeIdx.
        bool pcAttackDone = false;
        {
            u8 st = extra->model.anim.status;
            /* Anim_PlaybackOnce transitions status AND sets kf=endKf atomically.
             * On the frame the fire anim (73=Unk36 true) ends, we see the blend
             * target status (60=Unk30 false) but kf is still at the fire anim's
             * end frame. Remap blend-phase statuses to their source fire anim so
             * the endKf lookup is correct. */
            u8 lookupSt = st;
            /* Only remap in gun context. Multi-tap melee (knife/pipe) sets
             * anim.status = animAttack_7 - 2 = Unk30(false)=60 as its STARTING
             * status, not as a gun-blend-target. Remapping it to Unk36(true)
             * makes the lookup hit the wrong HARRY_BASE_ANIM_INFOS entry and
             * pcAttackDone fires prematurely — multi-tap combo aborts mid-swing. */
            if ((st == ANIM_STATUS(HarryAnim_Unk30, false) ||
                 st == ANIM_STATUS(HarryAnim_Unk36, false)) &&
                g_SysWork.playerCombat.weaponAttack >= WEAPON_ATTACK(EquippedWeaponId_Handgun, AttackInputType_Tap))
            {
                lookupSt = ANIM_STATUS(HarryAnim_Unk36, true);
            }
            if ((lookupSt == ANIM_STATUS(HarryAnim_Unk30, true) ||
                 lookupSt == ANIM_STATUS(HarryAnim_Unk36, true) ||
                 lookupSt == ANIM_STATUS(HarryAnim_HandgunRecoil, true) ||
                 lookupSt == ANIM_STATUS(HarryAnim_Unk29, true) ||
                 lookupSt == ANIM_STATUS(HarryAnim_Unk34, true)) &&
                lookupSt < 76)
            {
                const s_AnimInfo* info = &HARRY_BASE_ANIM_INFOS[lookupSt];
                bool isBackward = !info->hasVariableDuration && info->duration.constant < 0;
                s16 doneKf = isBackward ? info->startKeyframeIdx : info->endKeyframeIdx;
                if (doneKf > 0 && (isBackward ? extra->model.anim.keyframeIdx <= doneKf
                                             : extra->model.anim.keyframeIdx >= doneKf))
                {
                    pcAttackDone = true;
                    SH_DBG("[ATTACK-DONE] st=%d lookupSt=%d kf=%d -> pcAttackDone", (int)st, (int)lookupSt, (int)doneKf);
                }
            }
        }
#endif
        if (g_SysWork.playerCombat.weaponAttack < WEAPON_ATTACK(EquippedWeaponId_Handgun, AttackInputType_Tap))
        {
            // Attack anim.
            if (extra->model.anim.status == ANIM_STATUS(HarryAnim_Unk29, true) ||
                extra->model.anim.status == ANIM_STATUS(HarryAnim_Unk30, true) ||
                extra->model.anim.status == ANIM_STATUS(HarryAnim_HandgunRecoil, true) ||
                extra->model.anim.status == ANIM_STATUS(HarryAnim_Unk29, true) ||
                extra->model.anim.status == ANIM_STATUS(HarryAnim_Unk30, true) ||
                extra->model.anim.status == ANIM_STATUS(HarryAnim_HandgunRecoil, true) ||
                extra->model.anim.status == ANIM_STATUS(HarryAnim_Unk29, true) ||
                extra->model.anim.status == ANIM_STATUS(HarryAnim_Unk30, true) ||
                extra->model.anim.status == ANIM_STATUS(HarryAnim_HandgunRecoil, true))
            {
                if (
#ifdef SH_PC_PORT
                    /* Rely SOLELY on pcAttackDone (derived from the verified-good
                     * HARRY_BASE_ANIM_INFOS endKeyframeIdx). The old
                     * `keyframeIdx == D_800C44F0[..].field_6` term read the corrupt
                     * PC-reconstructed D_800294F4 table: e.g. for the SteelPipe it
                     * yields 597, which lands INSIDE the 584->613 swing and cut the
                     * swing at waist height. The outer guard only admits the active
                     * swing statuses (Unk29/Unk30/HandgunRecoil = 59/61/63), all
                     * covered by pcAttackDone, which fires at each swing's true end
                     * keyframe — full arc to the ground, FPS-independent. */
                    pcAttackDone
#else
                    extra->model.anim.keyframeIdx == D_800C44F0[D_800AF220].field_6
#endif
                    )
                {
                    extra->model.anim.status      = ANIM_STATUS(HarryAnim_HandgunAim, true);
#ifdef SH_PC_PORT
                    /* PC fix: use the aim-hold anim's endKf instead of
                     * D_800C44F0[0].field_6 (which for melee weapons is
                     * outside the HandgunAim range — e.g. knife wants
                     * kf=575 but field_6=587). Setting kf out of range
                     * shows a 1-frame snap before Anim_PlaybackOnce
                     * clamps it; the snap looks like the swing got cut
                     * off mid-way during multi-tap combo. */
                    extra->model.anim.keyframeIdx = HARRY_BASE_ANIM_INFOS[ANIM_STATUS(HarryAnim_HandgunAim, true)].endKeyframeIdx;
#else
                    extra->model.anim.keyframeIdx = D_800C44F0[0].field_6;
#endif
                    extra->model.anim.time         = Q12(extra->model.anim.keyframeIdx);

                    if (playerProps.flags & PlayerFlag_Unk0)
                    {
                        g_SysWork.playerWork.extra.state          = PlayerState_Combat;
                        g_SysWork.playerWork.extra.upperBodyState = PlayerUpperBodyState_AimTargetLock;

                        if (g_SysWork.playerWork.extra.lowerBodyState == PlayerLowerBodyState_Attack)
                        {
                            g_SysWork.playerWork.extra.lowerBodyState = PlayerLowerBodyState_Aim;
                        }
                    }
                    else
                    {
                        g_SysWork.playerWork.extra.state          = PlayerState_None;
                        g_SysWork.playerWork.extra.upperBodyState = PlayerUpperBodyState_Aim;
                        extra->model.controlState                          = extra->model.stateStep = 0;

                        if (g_SysWork.playerWork.extra.lowerBodyState == PlayerLowerBodyState_Attack)
                        {
                            g_SysWork.playerWork.extra.lowerBodyState             = PlayerLowerBodyState_Aim;
                            playerProps.flags &= ~PlayerFlag_Unk10;
                        }
                    }

                    playerProps.field_104  = 0;
                    playerProps.flags &= ~PlayerFlag_Unk2;
                    playerProps.flags &= ~PlayerFlag_Shooting;
                    g_SysWork.playerCombat.weaponAttack                = WEAPON_ATTACK(WEAPON_ATTACK_ID_GET(g_SysWork.playerCombat.weaponAttack), AttackInputType_Tap);
#ifdef SH_PC_PORT
                    /* Melee single-tap = single swing: after a melee swing
                     * completes, drain the attack shift register so a stale
                     * IsShooting bit (which persists ~2 game ticks past button
                     * release in the 2-bit register) can't re-open the fire
                     * gate via pcAtEndOfActive and dispatch a phantom STAB
                     * follow-up. The next swing now requires a fresh button
                     * click. Chainsaw / RockDrill keep their continuous-attack
                     * behavior — they reach this branch only when the user has
                     * stopped pressing, so draining their register is harmless.
                     * Gun follow-ups (Unk36 → Unk30) use the line ~3770 branch,
                     * not this one, so this clear doesn't affect handgun. */
                    {
                        u8 wid = (u8)WEAPON_ATTACK_ID_GET(g_SysWork.playerCombat.weaponAttack);
                        if (wid < EquippedWeaponId_Handgun) {
                            g_Player_IsShooting    = 0;
                            g_Player_IsAttacking   = 0;
                            s_pcMtClickQueue       = 0;
                            if (g_Controller0->heldBtnFlags &
                                g_GameWorkPtr->config.controllerConfig.action)
                            {
                                /* Button still down: keep the FULL hold history
                                 * (PSX never drains the register). With 0x1F the
                                 * eventual release walks 11110→11100→… which the
                                 * tap detector's !(hold & 0x11) mask rejects as
                                 * end-of-long-hold — no phantom slash. Draining
                                 * to 0 here (old code) made a 1-tick tail of the
                                 * continuing hold read as a fresh TAP on release,
                                 * which was the "extra swing when you let go at a
                                 * bad time" bug. 0x1F also lets hold-jab refill
                                 * IsAttacking next tick instead of 4 ticks later. */
                                g_Player_IsHoldAttack = 0x1F;
                            }
                            else
                            {
                                g_Player_IsHoldAttack = 0;
                                s_pcMeleeNeedsRelease = true;
                            }
                        }
                    }
#endif
                    return true;
                }
            }
        }
        // Attack anim.
        else if (
#ifdef SH_PC_PORT
                 pcAttackDone ||
#endif
                 ((extra->model.anim.status == ANIM_STATUS(HarryAnim_Unk30, true) ||
                  extra->model.anim.status == ANIM_STATUS(HarryAnim_Unk36, true)) &&
                 extra->model.anim.keyframeIdx == D_800C44F0[D_800AF220].field_6))
        {
            if (playerProps.flags & PlayerFlag_Unk0)
            {
                g_SysWork.playerWork.extra.state          = PlayerState_Combat;
                g_SysWork.playerWork.extra.upperBodyState = PlayerUpperBodyState_AimTargetLock;

                if (g_SysWork.playerWork.extra.lowerBodyState == PlayerLowerBodyState_Attack)
                {
                    g_SysWork.playerWork.extra.lowerBodyState = PlayerLowerBodyState_Aim;
                }
            }
            else
            {
                g_SysWork.playerWork.extra.state          = PlayerState_None;
                g_SysWork.playerWork.extra.upperBodyState = PlayerUpperBodyState_Aim;
                extra->model.controlState                          = extra->model.stateStep = 0;

                if (g_SysWork.playerWork.extra.lowerBodyState == PlayerLowerBodyState_Attack)
                {
                    g_SysWork.playerWork.extra.lowerBodyState             = PlayerLowerBodyState_Aim;
                    playerProps.flags &= ~PlayerFlag_Unk10;
                    player->model.controlState                                      =
                    player->model.stateStep                                  = 0;
                }
            }

            D_800C4556                                                  = NO_VALUE;
            D_800C4554                                                  = NO_VALUE;
            playerProps.field_104  = 0;
            playerProps.flags &= ~PlayerFlag_Shooting;
#ifdef SH_PC_PORT
            /* PSX continuous-fire cadence: on PSX the Aim state handler runs
             * for at least one frame between attack cycles and sets
             * PlayerFlag_Unk11 (status was mid-attack-anim AND fire still held),
             * which routes the next fire through the shorter Unk30 recoil
             * (kf 594→604, just the gun-extension portion) instead of the full
             * Unk36 (kf 582→604, gun raise + extend + recoil). On PC, the fire
             * gate's pc-override re-dispatches the next fire BEFORE the Aim
             * handler ever runs — Unk11 never gets set, every cycle replays
             * Unk36, and we used to snap status back to HandgunAim kf=579 (gun
             * yanked close to body) producing the visible jerk between shots.
             * Set Unk11 here directly so follow-up shots use Unk30 (gun stays
             * extended) and skip the snap entirely. */
            if (g_Player_IsAttacking || g_Player_IsShooting) {
                playerProps.flags |= PlayerFlag_Unk11;
            }
#endif
            return true;
        }

        playerProps.flags |= PlayerFlag_Unk6;

        // Handles multitap attack.
        if (g_SysWork.playerCombat.weaponAttack < WEAPON_ATTACK(EquippedWeaponId_Handgun, AttackInputType_Tap))
        {
            if (g_Player_MeleeAttackType == 0 && g_SysWork.playerCombat.weaponAttack != WEAPON_ATTACK(EquippedWeaponId_RockDrill, AttackInputType_Tap))
            {
                if (extra->model.anim.keyframeIdx >= keyframeIdx1 &&
                    extra->model.anim.keyframeIdx < keyframeIdx0 &&
                    extra->model.anim.status == ANIM_STATUS(HarryAnim_HandgunRecoil, true) &&
#ifdef SH_PC_PORT
                    s_pcMtClickQueue > 0 && !g_Player_IsMultiTapAttack)
#else
                    (g_Player_IsAttacking || g_Player_IsShooting))
#endif
                {
                    g_Player_IsMultiTapAttack = true;
#ifdef SH_PC_PORT
                    /* Consume the click that triggered this multi-tap. */
                    s_pcMtClickQueue--;
#endif
                }
            }
        }

        if (g_Player_IsMultiTapAttack)
        {
            if (extra->model.anim.status == ANIM_STATUS(HarryAnim_HandgunRecoil, true) &&
                extra->model.anim.keyframeIdx >= keyframeIdx0)
            {
                extra->model.stateStep = 0;

                if (g_SysWork.playerWork.extra.lowerBodyState == PlayerLowerBodyState_Attack)
                {
                    player->model.stateStep = 0;
                }

                g_Player_AttackAnimIdx                       = g_Player_EquippedWeaponInfo.animAttackHold - 2;
                D_800AF220                                   = (g_Player_EquippedWeaponInfo.field_A >> 4) - 1;
                g_Player_MeleeAttackType                     = 2;
                g_SysWork.playerCombat.weaponAttack = WEAPON_ATTACK(WEAPON_ATTACK_ID_GET(weaponAttack), AttackInputType_Multitap);

                if (extra->model.stateStep == 0)
                {
                    extra->model.anim.status = g_Player_EquippedWeaponInfo.animAttack - 2;
                    extra->model.stateStep++;
                }

                D_800C44D0 = HARRY_BASE_ANIM_INFOS[g_Player_AttackAnimIdx].startKeyframeIdx + D_800AD4C8[g_SysWork.playerCombat.weaponAttack].field_E;
                D_800C44D4 = HARRY_BASE_ANIM_INFOS[g_Player_AttackAnimIdx].startKeyframeIdx + D_800AD4C8[g_SysWork.playerCombat.weaponAttack].field_E +
                             D_800AD4C8[g_SysWork.playerCombat.weaponAttack].field_F;
                g_Player_IsMultiTapAttack = 0;

                playerProps.flags &= ~PlayerFlag_Unk2;
            }
        }

        return false;
