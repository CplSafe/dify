'use client'
/* eslint-disable no-alert, tailwindcss/enforce-consistent-class-order, tailwindcss/no-unknown-classes -- This admin screen follows the existing lightweight admin pages and uses native confirmations for review actions. */

import type {
  Agent,
  AgentCreateBody,
  ConsumptionRow,
  RebateRecord,
  RebindRequest,
  WithdrawalRequest,
} from '@/contract/console/admin-agent'
import {
  RiAddLine,
  RiBankCardLine,
  RiCheckLine,
  RiCloseLine,
  RiExchangeLine,
  RiFileList3Line,
  RiMoneyCnyCircleLine,
  RiShieldUserLine,
  RiUserAddLine,
} from '@remixicon/react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from '@/app/components/base/ui/toast'
import { useAppContext } from '@/context/app-context'
import { useRouter } from '@/next/navigation'
import {
  useAdminAgentConsumption,
  useAdminAgents,
  useAdminRebateRecords,
  useAdminRebindRequests,
  useAdminWithdrawalRequests,
  useCreateAdminAgent,
  useReviewRebindRequest,
  useReviewWithdrawalRequest,
  useSuspendAdminAgent,
} from '@/service/use-admin-agent'
import { cn } from '@/utils/classnames'

type TabKey = 'agents' | 'overview' | 'withdrawals' | 'rebinds' | 'rebates'

const PAGE_SIZE = 20

const tabs: Array<{ key: TabKey, label: string, icon: typeof RiShieldUserLine }> = [
  { key: 'agents', label: '代理商', icon: RiShieldUserLine },
  { key: 'overview', label: '消费概览', icon: RiMoneyCnyCircleLine },
  { key: 'withdrawals', label: '提现审核', icon: RiBankCardLine },
  { key: 'rebinds', label: '改绑审核', icon: RiExchangeLine },
  { key: 'rebates', label: '返佣记录', icon: RiFileList3Line },
]

const statusText = {
  active: '生效中',
  suspended: '已停用',
  pending: '待审核',
  approved: '已通过',
  rejected: '已拒绝',
  paid: '已打款',
}

const levelText = {
  national: '全国',
  province: '省级',
  city: '城市',
}

const payoutText = {
  alipay: '支付宝',
  wechat: '微信',
  bank: '银行卡',
}

const formatMoney = (value: string | number | null | undefined) => {
  const number = Number.parseFloat(String(value ?? 0))
  if (!Number.isFinite(number))
    return '0.00'
  return number.toFixed(2)
}

const formatDate = (value: string | null | undefined) => {
  if (!value)
    return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime()))
    return value
  return date.toLocaleDateString('zh-CN')
}

const statusBadgeClass = (status: string) => {
  if (status === 'active' || status === 'approved' || status === 'paid')
    return 'bg-state-success-hover text-state-success-text'
  if (status === 'pending')
    return 'bg-state-warning-hover text-state-warning-text'
  return 'bg-state-destructive-hover text-state-destructive-text'
}

const getErrorMessage = (error: unknown) =>
  error instanceof Error ? error.message : '操作失败，请稍后重试'

const StatusBadge = ({ status }: { status: string }) => (
  <span className={cn('inline-flex rounded-full px-2 py-0.5 text-xs font-medium', statusBadgeClass(status))}>
    {statusText[status as keyof typeof statusText] ?? status}
  </span>
)

const EmptyState = ({ text }: { text: string }) => (
  <div className="rounded-lg border border-dashed border-divider-subtle bg-background-default py-10 text-center text-sm text-text-tertiary">
    {text}
  </div>
)

const LoadingState = () => (
  <div className="rounded-lg border border-divider-subtle bg-background-default py-10 text-center text-sm text-text-tertiary">
    加载中...
  </div>
)

const Section = ({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: React.ReactNode
}) => (
  <section className="space-y-4">
    <div>
      <h2 className="text-base font-semibold text-text-primary">{title}</h2>
      {description && (
        <p className="mt-1 text-sm text-text-tertiary">{description}</p>
      )}
    </div>
    {children}
  </section>
)

const Metric = ({ label, value }: { label: string, value: string }) => (
  <div className="rounded-lg border border-divider-subtle bg-background-default p-4">
    <div className="text-xs font-medium text-text-tertiary">{label}</div>
    <div className="mt-2 text-xl font-semibold text-text-primary">{value}</div>
  </div>
)

const CreateAgentForm = () => {
  const createAgent = useCreateAdminAgent()
  const [form, setForm] = useState<AgentCreateBody>({
    account_id: '',
    name: '',
    rebate_rate: '',
    level: null,
    region_province: '',
    region_city: '',
    contact_phone: '',
    notes: '',
  })

  const setField = <K extends keyof AgentCreateBody>(key: K, value: AgentCreateBody[K]) => {
    setForm(prev => ({ ...prev, [key]: value }))
  }

  const handleSubmit = () => {
    const body: AgentCreateBody = {
      account_id: form.account_id.trim(),
      name: form.name.trim(),
      rebate_rate: form.rebate_rate || null,
      level: form.level || null,
      region_province: form.region_province || null,
      region_city: form.region_city || null,
      contact_phone: form.contact_phone || null,
      notes: form.notes || null,
    }
    if (!body.account_id || !body.name) {
      toast.error('请填写账号 ID 和代理商名称')
      return
    }
    createAgent.mutate(body, {
      onSuccess: () => {
        toast.success('代理商已开通')
        setForm({
          account_id: '',
          name: '',
          rebate_rate: '',
          level: null,
          region_province: '',
          region_city: '',
          contact_phone: '',
          notes: '',
        })
      },
      onError: err => toast.error(getErrorMessage(err)),
    })
  }

  return (
    <div className="rounded-lg border border-divider-subtle bg-background-default p-5">
      <div className="mb-4 flex items-center gap-2">
        <RiUserAddLine className="h-5 w-5 text-text-accent" />
        <h2 className="text-base font-semibold text-text-primary">开通代理商</h2>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <label className="space-y-1">
          <span className="text-xs font-medium text-text-secondary">账号 ID</span>
          <input
            value={form.account_id}
            onChange={e => setField('account_id', e.target.value)}
            placeholder="粘贴 accounts.id"
            className="w-full rounded-md border border-components-input-border-normal bg-components-input-bg-normal px-3 py-2 text-sm outline-none focus:border-components-input-border-active"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-text-secondary">代理商名称</span>
          <input
            value={form.name}
            onChange={e => setField('name', e.target.value)}
            placeholder="例如：深圳一区代理"
            className="w-full rounded-md border border-components-input-border-normal bg-components-input-bg-normal px-3 py-2 text-sm outline-none focus:border-components-input-border-active"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-text-secondary">返佣比例</span>
          <input
            value={form.rebate_rate ?? ''}
            onChange={e => setField('rebate_rate', e.target.value)}
            placeholder="0.1000"
            className="w-full rounded-md border border-components-input-border-normal bg-components-input-bg-normal px-3 py-2 text-sm outline-none focus:border-components-input-border-active"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-text-secondary">级别</span>
          <select
            value={form.level ?? ''}
            onChange={e => setField('level', e.target.value ? e.target.value as AgentCreateBody['level'] : null)}
            className="w-full rounded-md border border-components-input-border-normal bg-components-input-bg-normal px-3 py-2 text-sm outline-none focus:border-components-input-border-active"
          >
            <option value="">未设置</option>
            <option value="national">全国</option>
            <option value="province">省级</option>
            <option value="city">城市</option>
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-text-secondary">省份</span>
          <input
            value={form.region_province ?? ''}
            onChange={e => setField('region_province', e.target.value)}
            placeholder="广东省"
            className="w-full rounded-md border border-components-input-border-normal bg-components-input-bg-normal px-3 py-2 text-sm outline-none focus:border-components-input-border-active"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-text-secondary">城市</span>
          <input
            value={form.region_city ?? ''}
            onChange={e => setField('region_city', e.target.value)}
            placeholder="深圳市"
            className="w-full rounded-md border border-components-input-border-normal bg-components-input-bg-normal px-3 py-2 text-sm outline-none focus:border-components-input-border-active"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-text-secondary">联系方式</span>
          <input
            value={form.contact_phone ?? ''}
            onChange={e => setField('contact_phone', e.target.value)}
            placeholder="手机号"
            className="w-full rounded-md border border-components-input-border-normal bg-components-input-bg-normal px-3 py-2 text-sm outline-none focus:border-components-input-border-active"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-text-secondary">备注</span>
          <input
            value={form.notes ?? ''}
            onChange={e => setField('notes', e.target.value)}
            placeholder="可选"
            className="w-full rounded-md border border-components-input-border-normal bg-components-input-bg-normal px-3 py-2 text-sm outline-none focus:border-components-input-border-active"
          />
        </label>
      </div>
      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          disabled={createAgent.isPending}
          onClick={handleSubmit}
          className="inline-flex items-center gap-1 rounded-md bg-components-button-primary-bg px-4 py-2 text-sm font-medium text-components-button-primary-text disabled:opacity-50"
        >
          <RiAddLine className="h-4 w-4" />
          {createAgent.isPending ? '开通中...' : '开通代理商'}
        </button>
        <span className="text-xs text-text-tertiary">
          开通后该账号重新登录即可访问 /agent/dashboard。
        </span>
      </div>
    </div>
  )
}

const AgentsTable = () => {
  const [status, setStatus] = useState<'active' | 'suspended' | undefined>()
  const agents = useAdminAgents({ page: 1, limit: PAGE_SIZE, status })
  const suspendAgent = useSuspendAdminAgent()

  const handleSuspend = (agent: Agent) => {
    if (!confirm(`确认停用代理商「${agent.name}」？停用后邀请码将不可用。`))
      return
    suspendAgent.mutate(agent.id, {
      onSuccess: () => toast.success('代理商已停用'),
      onError: err => toast.error(getErrorMessage(err)),
    })
  }

  return (
    <Section title="代理商列表" description="开通代理商身份，并查看当前代理商状态。">
      <div className="flex flex-wrap items-center gap-2">
        {[
          { label: '全部', value: undefined },
          { label: '生效中', value: 'active' as const },
          { label: '已停用', value: 'suspended' as const },
        ].map(item => (
          <button
            key={item.label}
            type="button"
            onClick={() => setStatus(item.value)}
            className={cn(
              'rounded-md border px-3 py-1.5 text-sm',
              status === item.value
                ? 'border-components-button-primary-bg bg-state-accent-active text-text-accent'
                : 'border-divider-subtle text-text-secondary hover:bg-state-base-hover',
            )}
          >
            {item.label}
          </button>
        ))}
      </div>
      {agents.isLoading
        ? <LoadingState />
        : !agents.data?.data.length
            ? <EmptyState text="暂无代理商" />
            : (
                <div className="overflow-x-auto rounded-lg border border-divider-subtle bg-background-default">
                  <table className="min-w-[960px] w-full text-sm">
                    <thead className="bg-background-default-dimm">
                      <tr>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">代理商</th>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">账号 ID</th>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">区域</th>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">返佣</th>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">状态</th>
                        <th className="px-4 py-3 text-right font-medium text-text-secondary">操作</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-divider-subtle">
                      {agents.data.data.map(agent => (
                        <tr key={agent.id} className="hover:bg-background-default-dimm">
                          <td className="px-4 py-3">
                            <div className="font-medium text-text-primary">{agent.name}</div>
                            <div className="text-xs text-text-tertiary">{agent.contact_phone || '未填写联系方式'}</div>
                          </td>
                          <td className="px-4 py-3 font-mono text-xs text-text-tertiary">{agent.account_id}</td>
                          <td className="px-4 py-3 text-text-secondary">
                            {agent.level ? levelText[agent.level] : '未设置'}
                            {(agent.region_province || agent.region_city) && (
                              <span className="ml-1 text-text-tertiary">
                                {agent.region_province ?? ''}
                                {agent.region_city ?? ''}
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-text-secondary">{agent.rebate_rate ?? '-'}</td>
                          <td className="px-4 py-3"><StatusBadge status={agent.status} /></td>
                          <td className="px-4 py-3 text-right">
                            {agent.status === 'active'
                              ? (
                                  <button
                                    type="button"
                                    disabled={suspendAgent.isPending}
                                    onClick={() => handleSuspend(agent)}
                                    className="rounded-md border border-state-destructive-border px-3 py-1.5 text-xs text-state-destructive-text hover:bg-state-destructive-hover disabled:opacity-50"
                                  >
                                    停用
                                  </button>
                                )
                              : <span className="text-xs text-text-tertiary">无操作</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
    </Section>
  )
}

const OverviewTable = () => {
  const overview = useAdminAgentConsumption()
  const rows = useMemo(() => overview.data?.data ?? [], [overview.data?.data])
  const totals = useMemo(() => rows.reduce(
    (acc, row) => ({
      invitees: acc.invitees + row.invitee_count,
      withdrawable: acc.withdrawable + Number.parseFloat(row.withdrawable || '0'),
      earned: acc.earned + Number.parseFloat(row.total_earned || '0'),
      consumption: acc.consumption + Number.parseFloat(row.last_30d_consumption || '0'),
    }),
    { invitees: 0, withdrawable: 0, earned: 0, consumption: 0 },
  ), [rows])

  return (
    <Section title="消费概览" description="按代理商汇总被邀请用户、可提现余额和近 30 天消费。">
      <div className="grid gap-3 md:grid-cols-4">
        <Metric label="代理商数" value={String(rows.length)} />
        <Metric label="邀请用户数" value={String(totals.invitees)} />
        <Metric label="可提现合计" value={formatMoney(totals.withdrawable)} />
        <Metric label="近 30 天消费" value={formatMoney(totals.consumption)} />
      </div>
      {overview.isLoading
        ? <LoadingState />
        : !rows.length
            ? <EmptyState text="暂无消费数据" />
            : (
                <div className="overflow-x-auto rounded-lg border border-divider-subtle bg-background-default">
                  <table className="min-w-[920px] w-full text-sm">
                    <thead className="bg-background-default-dimm">
                      <tr>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">代理商</th>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">状态</th>
                        <th className="px-4 py-3 text-right font-medium text-text-secondary">邀请用户</th>
                        <th className="px-4 py-3 text-right font-medium text-text-secondary">可提现</th>
                        <th className="px-4 py-3 text-right font-medium text-text-secondary">累计返佣</th>
                        <th className="px-4 py-3 text-right font-medium text-text-secondary">近 30 天消费</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-divider-subtle">
                      {rows.map((row: ConsumptionRow) => (
                        <tr key={row.agent_id} className="hover:bg-background-default-dimm">
                          <td className="px-4 py-3">
                            <div className="font-medium text-text-primary">{row.name}</div>
                            <div className="text-xs text-text-tertiary">
                              {row.level ? row.level : '未设置级别'}
                              {' '}
                              {row.region_province ?? ''}
                              {row.region_city ?? ''}
                            </div>
                          </td>
                          <td className="px-4 py-3"><StatusBadge status={row.status} /></td>
                          <td className="px-4 py-3 text-right text-text-secondary">{row.invitee_count}</td>
                          <td className="px-4 py-3 text-right text-text-primary">{formatMoney(row.withdrawable)}</td>
                          <td className="px-4 py-3 text-right text-text-secondary">{formatMoney(row.total_earned)}</td>
                          <td className="px-4 py-3 text-right text-text-secondary">{formatMoney(row.last_30d_consumption)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
    </Section>
  )
}

const WithdrawalsTable = () => {
  const withdrawals = useAdminWithdrawalRequests({ page: 1, limit: PAGE_SIZE, status: 'pending' })
  const review = useReviewWithdrawalRequest()

  const handlePay = (request: WithdrawalRequest) => {
    const transactionId = window.prompt('请输入打款流水号')
    if (!transactionId)
      return
    review.mutate({ request, action: 'pay', transactionId }, {
      onSuccess: () => toast.success('提现申请已标记为已打款'),
      onError: err => toast.error(getErrorMessage(err)),
    })
  }

  const handleReject = (request: WithdrawalRequest) => {
    const note = window.prompt('请输入拒绝原因')
    if (!note)
      return
    review.mutate({ request, action: 'reject', note }, {
      onSuccess: () => toast.success('提现申请已拒绝'),
      onError: err => toast.error(getErrorMessage(err)),
    })
  }

  return (
    <Section title="提现审核" description="处理代理商提交的待审核提现申请。">
      {withdrawals.isLoading
        ? <LoadingState />
        : !withdrawals.data?.data.length
            ? <EmptyState text="暂无待审核提现" />
            : (
                <div className="overflow-x-auto rounded-lg border border-divider-subtle bg-background-default">
                  <table className="min-w-[900px] w-full text-sm">
                    <thead className="bg-background-default-dimm">
                      <tr>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">申请 ID</th>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">代理商 ID</th>
                        <th className="px-4 py-3 text-right font-medium text-text-secondary">金额</th>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">方式</th>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">申请时间</th>
                        <th className="px-4 py-3 text-right font-medium text-text-secondary">操作</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-divider-subtle">
                      {withdrawals.data.data.map(request => (
                        <tr key={request.id} className="hover:bg-background-default-dimm">
                          <td className="px-4 py-3 font-mono text-xs text-text-tertiary">{request.id}</td>
                          <td className="px-4 py-3 font-mono text-xs text-text-tertiary">{request.agent_id}</td>
                          <td className="px-4 py-3 text-right font-medium text-text-primary">{formatMoney(request.amount)}</td>
                          <td className="px-4 py-3 text-text-secondary">{payoutText[request.payout_method]}</td>
                          <td className="px-4 py-3 text-text-secondary">{formatDate(request.created_at)}</td>
                          <td className="px-4 py-3">
                            <div className="flex justify-end gap-2">
                              <button
                                type="button"
                                disabled={review.isPending}
                                onClick={() => handlePay(request)}
                                className="inline-flex items-center gap-1 rounded-md border border-state-success-border px-3 py-1.5 text-xs text-state-success-text hover:bg-state-success-hover disabled:opacity-50"
                              >
                                <RiCheckLine className="h-3.5 w-3.5" />
                                已打款
                              </button>
                              <button
                                type="button"
                                disabled={review.isPending}
                                onClick={() => handleReject(request)}
                                className="inline-flex items-center gap-1 rounded-md border border-state-destructive-border px-3 py-1.5 text-xs text-state-destructive-text hover:bg-state-destructive-hover disabled:opacity-50"
                              >
                                <RiCloseLine className="h-3.5 w-3.5" />
                                拒绝
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
    </Section>
  )
}

const RebindsTable = () => {
  const rebinds = useAdminRebindRequests({ page: 1, limit: PAGE_SIZE, status: 'pending' })
  const review = useReviewRebindRequest()

  const handleReview = (request: RebindRequest, action: 'approve' | 'reject') => {
    const note = window.prompt(action === 'approve' ? '审批备注（可选）' : '请输入拒绝原因')
    if (action === 'reject' && !note)
      return
    review.mutate({ requestId: request.id, action, note: note ?? undefined }, {
      onSuccess: () => toast.success(action === 'approve' ? '改绑申请已通过' : '改绑申请已拒绝'),
      onError: err => toast.error(getErrorMessage(err)),
    })
  }

  return (
    <Section title="改绑审核" description="处理用户从原代理商改绑到新代理商的申请。">
      {rebinds.isLoading
        ? <LoadingState />
        : !rebinds.data?.data.length
            ? <EmptyState text="暂无待审核改绑申请" />
            : (
                <div className="overflow-x-auto rounded-lg border border-divider-subtle bg-background-default">
                  <table className="min-w-[900px] w-full text-sm">
                    <thead className="bg-background-default-dimm">
                      <tr>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">申请 ID</th>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">用户 ID</th>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">原代理商</th>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">新代理商</th>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">申请时间</th>
                        <th className="px-4 py-3 text-right font-medium text-text-secondary">操作</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-divider-subtle">
                      {rebinds.data.data.map(request => (
                        <tr key={request.id} className="hover:bg-background-default-dimm">
                          <td className="px-4 py-3 font-mono text-xs text-text-tertiary">{request.id}</td>
                          <td className="px-4 py-3 font-mono text-xs text-text-tertiary">{request.account_id}</td>
                          <td className="px-4 py-3 font-mono text-xs text-text-tertiary">{request.from_agent_id}</td>
                          <td className="px-4 py-3 font-mono text-xs text-text-tertiary">{request.to_agent_id}</td>
                          <td className="px-4 py-3 text-text-secondary">{formatDate(request.created_at)}</td>
                          <td className="px-4 py-3">
                            <div className="flex justify-end gap-2">
                              <button
                                type="button"
                                disabled={review.isPending}
                                onClick={() => handleReview(request, 'approve')}
                                className="inline-flex items-center gap-1 rounded-md border border-state-success-border px-3 py-1.5 text-xs text-state-success-text hover:bg-state-success-hover disabled:opacity-50"
                              >
                                <RiCheckLine className="h-3.5 w-3.5" />
                                通过
                              </button>
                              <button
                                type="button"
                                disabled={review.isPending}
                                onClick={() => handleReview(request, 'reject')}
                                className="inline-flex items-center gap-1 rounded-md border border-state-destructive-border px-3 py-1.5 text-xs text-state-destructive-text hover:bg-state-destructive-hover disabled:opacity-50"
                              >
                                <RiCloseLine className="h-3.5 w-3.5" />
                                拒绝
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
    </Section>
  )
}

const RebatesTable = () => {
  const rebates = useAdminRebateRecords({ page: 1, limit: PAGE_SIZE })
  return (
    <Section title="返佣记录" description="查看最新的代理商返佣结算记录。">
      {rebates.isLoading
        ? <LoadingState />
        : !rebates.data?.data.length
            ? <EmptyState text="暂无返佣记录" />
            : (
                <div className="overflow-x-auto rounded-lg border border-divider-subtle bg-background-default">
                  <table className="min-w-[960px] w-full text-sm">
                    <thead className="bg-background-default-dimm">
                      <tr>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">记录 ID</th>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">代理商 ID</th>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">被邀请用户</th>
                        <th className="px-4 py-3 text-right font-medium text-text-secondary">消费</th>
                        <th className="px-4 py-3 text-right font-medium text-text-secondary">返佣</th>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">结算日</th>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">状态</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-divider-subtle">
                      {rebates.data.data.map((record: RebateRecord) => (
                        <tr key={record.id} className="hover:bg-background-default-dimm">
                          <td className="px-4 py-3 font-mono text-xs text-text-tertiary">{record.id}</td>
                          <td className="px-4 py-3 font-mono text-xs text-text-tertiary">{record.agent_id}</td>
                          <td className="px-4 py-3 font-mono text-xs text-text-tertiary">{record.invitee_account_id}</td>
                          <td className="px-4 py-3 text-right text-text-secondary">{formatMoney(record.consumption_amount)}</td>
                          <td className="px-4 py-3 text-right font-medium text-text-primary">{formatMoney(record.rebate_amount)}</td>
                          <td className="px-4 py-3 text-text-secondary">{record.settlement_date}</td>
                          <td className="px-4 py-3 text-text-secondary">{record.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
    </Section>
  )
}

export default function AdminAgentsPage() {
  const { isSystemAdmin, isLoadingCurrentWorkspace } = useAppContext()
  const router = useRouter()
  const [activeTab, setActiveTab] = useState<TabKey>('agents')

  useEffect(() => {
    if (!isLoadingCurrentWorkspace && !isSystemAdmin)
      router.replace('/apps')
  }, [isLoadingCurrentWorkspace, isSystemAdmin, router])

  if (!isSystemAdmin && !isLoadingCurrentWorkspace)
    return null

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-background-body">
      <div className="border-b border-divider-subtle bg-background-default px-8 py-6">
        <h1 className="text-2xl font-bold text-text-primary">代理商管理</h1>
        <p className="mt-1 text-sm text-text-tertiary">
          开通代理商身份，审核提现和改绑申请，并查看返佣与消费情况。
        </p>
      </div>

      <div className="flex-1 space-y-6 p-8">
        <CreateAgentForm />

        <div className="flex flex-wrap gap-2 border-b border-divider-subtle">
          {tabs.map((tab) => {
            const Icon = tab.icon
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActiveTab(tab.key)}
                className={cn(
                  'mb-[-1px] inline-flex items-center gap-1.5 border-b-2 px-3 py-3 text-sm font-medium transition-colors',
                  activeTab === tab.key
                    ? 'border-components-button-primary-bg text-text-accent'
                    : 'border-transparent text-text-tertiary hover:text-text-secondary',
                )}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </button>
            )
          })}
        </div>

        {activeTab === 'agents' && <AgentsTable />}
        {activeTab === 'overview' && <OverviewTable />}
        {activeTab === 'withdrawals' && <WithdrawalsTable />}
        {activeTab === 'rebinds' && <RebindsTable />}
        {activeTab === 'rebates' && <RebatesTable />}
      </div>
    </div>
  )
}
