'use client'
import type { InvitationResult } from '@/models/common'
import type { MemberBalance, WalletBalance } from '@/service/wallet'
import { RiCoinsLine } from '@remixicon/react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Avatar } from '@/app/components/base/avatar'
import Button from '@/app/components/base/button'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/app/components/base/ui/tooltip'
import { NUM_INFINITE } from '@/app/components/billing/config'
import { Plan } from '@/app/components/billing/type'
import UpgradeBtn from '@/app/components/billing/upgrade-btn'
import { useAppContext } from '@/context/app-context'
import { useGlobalPublicStore } from '@/context/global-public-context'
import { useLocale } from '@/context/i18n'
import { useProviderContext } from '@/context/provider-context'
import { useFormatTimeFromNow } from '@/hooks/use-format-time-from-now'
import { LanguagesSupported } from '@/i18n-config/language'
import { useMembers } from '@/service/use-common'
import { fetchWallet, listMemberBalances } from '@/service/wallet'
import AllocationModal from './allocation-modal'
import EditWorkspaceModal from './edit-workspace-modal'
import InviteButton from './invite-button'
import InviteModal from './invite-modal'
import InvitedModal from './invited-modal'
import Operation from './operation'
import TransferOwnership from './operation/transfer-ownership'
import TransferOwnershipModal from './transfer-ownership-modal'

const MembersPage = () => {
  const { t } = useTranslation()
  const RoleMap = {
    owner: t('members.owner', { ns: 'common' }),
    admin: t('members.admin', { ns: 'common' }),
    editor: t('members.editor', { ns: 'common' }),
    dataset_operator: t('members.datasetOperator', { ns: 'common' }),
    normal: t('members.normal', { ns: 'common' }),
  }
  const locale = useLocale()

  const { userProfile, currentWorkspace, isCurrentWorkspaceOwner }
    = useAppContext()
  const { data, refetch } = useMembers()
  const systemFeatures = useGlobalPublicStore(s => s.systemFeatures)
  const { formatTimeFromNow } = useFormatTimeFromNow()
  const [inviteModalVisible, setInviteModalVisible] = useState(false)
  const [invitationResults, setInvitationResults] = useState<
    InvitationResult[]
  >([])
  const [invitedModalVisible, setInvitedModalVisible] = useState(false)
  const accounts = data?.accounts || []
  const { plan, enableBilling, isAllowTransferWorkspace }
    = useProviderContext()
  const isNotUnlimitedMemberPlan
    = enableBilling && plan.type !== Plan.team && plan.type !== Plan.enterprise
  const isMemberFull
    = enableBilling
      && isNotUnlimitedMemberPlan
      && accounts.length >= plan.total.teamMembers
  const [editWorkspaceModalVisible, setEditWorkspaceModalVisible]
    = useState(false)
  const [showTransferOwnershipModal, setShowTransferOwnershipModal]
    = useState(false)

  // Owner-only: per-member wallet snapshot + workspace wallet. Both are
  // refetched after every allocation so the UI stays honest without a
  // hard page refresh. Non-owners never hit these endpoints (the backend
  // rejects them anyway).
  const [balances, setBalances] = useState<Map<string, MemberBalance>>(
    () => new Map(),
  )
  const [wallet, setWallet] = useState<WalletBalance | null>(null)
  const [allocationTarget, setAllocationTarget] = useState<{
    id: string
    name: string
    balance: string
  } | null>(null)

  const loadOwnerData = useCallback(async () => {
    if (!isCurrentWorkspaceOwner)
      return
    try {
      const [balanceList, walletSnapshot] = await Promise.all([
        listMemberBalances(),
        fetchWallet(),
      ])
      const next = new Map<string, MemberBalance>()
      for (const entry of balanceList.data) next.set(entry.account_id, entry)
      setBalances(next)
      setWallet(walletSnapshot)
    }
    catch {
      // Best-effort: members list still renders without the balance column.
    }
  }, [isCurrentWorkspaceOwner])

  useEffect(() => {
    void loadOwnerData()
  }, [loadOwnerData])

  // Owner row shows the workspace wallet (TenantBalance.balance) — owners
  // spend workspace funds directly and never hold a per-member UserBalance
  // pool (see backend AllocationService / UserBillingService.is_tenant_owner).
  // Non-owner rows show their UserBalance snapshot from listMemberBalances().
  const balanceFor = useMemo(
    () => (accountId: string, role: string | undefined) => {
      if (role === 'owner')
        return wallet?.tenant.balance ?? '0'
      return balances.get(accountId)?.balance ?? '0'
    },
    [balances, wallet],
  )

  return (
    <>
      <div className="flex flex-col">
        <div className="mb-4 flex items-center gap-3 rounded-xl border-l-[0.5px] border-t-[0.5px] border-divider-subtle bg-linear-to-r from-background-gradient-bg-fill-chat-bg-2 to-background-gradient-bg-fill-chat-bg-1 p-3 pr-5">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-components-icon-bg-blue-solid text-[20px]">
            <span className="bg-linear-to-r from-components-avatar-shape-fill-stop-0 to-components-avatar-shape-fill-stop-100 bg-clip-text font-semibold uppercase text-shadow-shadow-1 opacity-90">
              {currentWorkspace?.name[0]?.toLocaleUpperCase()}
            </span>
          </div>
          <div className="grow">
            <div className="flex items-center gap-1 system-md-semibold text-text-secondary">
              <span>{currentWorkspace?.name}</span>
              {isCurrentWorkspaceOwner && (
                <span>
                  <Tooltip>
                    <TooltipTrigger
                      render={(
                        <div
                          className="cursor-pointer rounded-md p-1 hover:bg-black/5"
                          onClick={() => {
                            setEditWorkspaceModalVisible(true)
                          }}
                        >
                          <div
                            data-testid="edit-workspace-pencil"
                            className="i-ri-pencil-line h-4 w-4 text-text-tertiary"
                          />
                        </div>
                      )}
                    />
                    <TooltipContent>
                      {t('account.editWorkspaceInfo', { ns: 'common' })}
                    </TooltipContent>
                  </Tooltip>
                </span>
              )}
            </div>
            <div className="mt-1 system-xs-medium text-text-tertiary">
              {enableBilling && isNotUnlimitedMemberPlan
                ? (
                    <div className="flex space-x-1">
                      <div>
                        {t('plansCommon.member', { ns: 'billing' })}
                        {locale !== LanguagesSupported[1]
                          && accounts.length > 1
                          && 's'}
                      </div>
                      <div className="">{accounts.length}</div>
                      <div>/</div>
                      <div>
                        {plan.total.teamMembers === NUM_INFINITE
                          ? t('plansCommon.unlimited', { ns: 'billing' })
                          : plan.total.teamMembers}
                      </div>
                    </div>
                  )
                : (
                    <div className="flex space-x-1">
                      <div>{accounts.length}</div>
                      <div>
                        {t('plansCommon.memberAfter', { ns: 'billing' })}
                        {locale !== LanguagesSupported[1]
                          && accounts.length > 1
                          && 's'}
                      </div>
                    </div>
                  )}
            </div>
          </div>
          {isMemberFull && <UpgradeBtn className="mr-2" loc="member-invite" />}
          <div className="shrink-0">
            {isCurrentWorkspaceOwner && (
              <InviteButton
                disabled={isMemberFull}
                onClick={() => setInviteModalVisible(true)}
              />
            )}
          </div>
        </div>
        <div className="overflow-visible lg:overflow-visible">
          <div className="flex min-w-[480px] items-center border-b border-divider-regular py-[7px]">
            <div className="grow px-3 system-xs-medium-uppercase text-text-tertiary">
              {t('members.name', { ns: 'common' })}
            </div>
            <div className="w-[104px] shrink-0 system-xs-medium-uppercase text-text-tertiary">
              {t('members.lastActive', { ns: 'common' })}
            </div>
            {isCurrentWorkspaceOwner && (
              <div className="w-[120px] shrink-0 px-3 text-right system-xs-medium-uppercase text-text-tertiary">
                余额
              </div>
            )}
            <div className="w-[96px] shrink-0 px-3 system-xs-medium-uppercase text-text-tertiary">
              {t('members.role', { ns: 'common' })}
            </div>
            {isCurrentWorkspaceOwner && (
              <div className="w-[104px] shrink-0 px-3 system-xs-medium-uppercase text-text-tertiary">
                额度
              </div>
            )}
          </div>
          <div className="relative min-w-[480px]">
            {accounts.map(account => (
              <div
                key={account.id}
                className="flex border-b border-divider-subtle"
              >
                <div className="flex grow items-center px-3 py-2">
                  <Avatar
                    avatar={account.avatar_url}
                    size="sm"
                    className="mr-2"
                    name={account.name}
                  />
                  <div className="">
                    <div className="system-sm-medium text-text-secondary">
                      {account.name}
                      {account.status === 'pending' && (
                        <span className="ml-1 system-xs-medium text-text-warning">
                          {t('members.pending', { ns: 'common' })}
                        </span>
                      )}
                      {userProfile.email === account.email && (
                        <span className="system-xs-regular text-text-tertiary">
                          {t('members.you', { ns: 'common' })}
                        </span>
                      )}
                    </div>
                    <div className="system-xs-regular text-text-tertiary">
                      {account.email}
                    </div>
                  </div>
                </div>
                <div className="flex w-[104px] shrink-0 items-center py-2 system-sm-regular text-text-secondary">
                  {formatTimeFromNow(
                    Number(account.last_active_at || account.created_at) * 1000,
                  )}
                </div>
                {isCurrentWorkspaceOwner && (
                  <div className="flex w-[120px] shrink-0 items-center justify-end px-3 py-2 text-right tabular-nums system-sm-regular text-text-secondary">
                    ¥
                    {Number(balanceFor(account.id, account.role)).toFixed(2)}
                  </div>
                )}
                <div className="flex w-[96px] shrink-0 items-center">
                  {isCurrentWorkspaceOwner
                    && account.role === 'owner'
                    && isAllowTransferWorkspace && (
                    <TransferOwnership
                      onOperate={() => setShowTransferOwnershipModal(true)}
                    >
                    </TransferOwnership>
                  )}
                  {isCurrentWorkspaceOwner
                    && account.role === 'owner'
                    && !isAllowTransferWorkspace && (
                    <div className="px-3 system-sm-regular text-text-secondary">
                      {RoleMap[account.role] || RoleMap.normal}
                    </div>
                  )}
                  {isCurrentWorkspaceOwner && account.role !== 'owner' && (
                    <Operation
                      member={account}
                      operatorRole={currentWorkspace.role}
                      onOperate={refetch}
                    />
                  )}
                  {!isCurrentWorkspaceOwner && (
                    <div className="px-3 system-sm-regular text-text-secondary">
                      {RoleMap[account.role] || RoleMap.normal}
                    </div>
                  )}
                </div>
                {isCurrentWorkspaceOwner && (
                  <div className="flex w-[104px] shrink-0 items-center px-3 py-2">
                    {account.role !== 'owner'
                      && account.status !== 'pending' && (
                      <Button
                        size="small"
                        onClick={() =>
                          setAllocationTarget({
                            id: account.id,
                            name: account.name,
                            balance: balanceFor(account.id, account.role),
                          })}
                      >
                        <RiCoinsLine className="mr-1 h-3.5 w-3.5" />
                        分配
                      </Button>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
      {inviteModalVisible && (
        <InviteModal
          isEmailSetup={systemFeatures.is_email_setup}
          onCancel={() => setInviteModalVisible(false)}
          onSend={(invitationResults) => {
            setInvitedModalVisible(true)
            setInvitationResults(invitationResults)
            refetch()
          }}
        />
      )}
      {invitedModalVisible && (
        <InvitedModal
          invitationResults={invitationResults}
          onCancel={() => setInvitedModalVisible(false)}
        />
      )}
      {editWorkspaceModalVisible && (
        <EditWorkspaceModal
          onCancel={() => setEditWorkspaceModalVisible(false)}
        />
      )}
      {showTransferOwnershipModal && (
        <TransferOwnershipModal
          show={showTransferOwnershipModal}
          onClose={() => setShowTransferOwnershipModal(false)}
        />
      )}
      {allocationTarget && (
        <AllocationModal
          open={allocationTarget !== null}
          onOpenChange={(next) => {
            if (!next)
              setAllocationTarget(null)
          }}
          memberId={allocationTarget.id}
          memberName={allocationTarget.name}
          memberBalance={allocationTarget.balance}
          tenantBalance={wallet?.tenant.balance}
          onSuccess={() => {
            void loadOwnerData()
          }}
        />
      )}
    </>
  )
}

export default MembersPage
