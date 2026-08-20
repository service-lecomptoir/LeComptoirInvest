import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Eye, Plus, ShieldAlert, ShieldCheck, ShieldQuestion, ShieldX, Users } from 'lucide-react'
import { investorsApi } from '@/api'
import { withOverageConsent } from '@/lib/overage'
import { Button, Input, Select } from '@/components/ui'
import {
  Card, EmptyState, Loading, Notice, PageHeader, Pill, TableWrap, Td, Th,
} from '@/components/common/Primitives'
import { day } from '@/lib/format'
import { toast } from '@/store/toast'
import type { InvestorCategory, InvestorQuota } from '@/types'

/** The four verdicts, exactly as `app/core/kyc.py` names them. The tone follows what each
 *  one DOES to money, not how pleasant it sounds: « pending » blocks just as hard as
 *  « refused », and showing it in grey would read as a formality. */
const KYC: Record<string, { tone: 'good' | 'warn' | 'bad' | 'neutral'; icon: typeof ShieldCheck }> = {
  accepted: { tone: 'good', icon: ShieldCheck },
  pending: { tone: 'warn', icon: ShieldQuestion },
  review: { tone: 'warn', icon: ShieldAlert },
  refused: { tone: 'bad', icon: ShieldX },
}

interface Row {
  id: string
  kind: string
  display_name: string
  email: string | null
  country_code: string | null
  kyc_status: string
  kyc_review_due_on: string | null
  has_bank_details: boolean
  //   Which protections apply. null means nobody assessed them, which the API reads as
  //   PROTECTED — so the column shows « not assessed » rather than an empty cell.
  category: InvestorCategory | null
  loss_bearing_capacity: string | null
}

export default function Investors() {
  const { t } = useTranslation()
  const [rows, setRows] = useState<Row[] | null>(null)
  const [creating, setCreating] = useState(false)
  const [deciding, setDeciding] = useState<Row | null>(null)
  const [assessing, setAssessing] = useState<Row | null>(null)
  const [bank, setBank] = useState<Record<string, { iban: string | null }>>({})
  const [quota, setQuota] = useState<InvestorQuota | null>(null)

  const load = () => {
    // ⚠️ RELOADED WITH THE REGISTER, NEVER ONCE AT MOUNT. Adding an investor is exactly
    // what moves this number, and a banner still reading « 48 of 50 » after the 50th was
    // registered would be the one screen in the product that lies about the plan.
    investorsApi.quota().then((r) => setQuota(r.data)).catch(() => setQuota(null))
    return investorsApi.list().then((r) => setRows(r.data as unknown as Row[])).catch(() => setRows([]))
  }
  useEffect(() => {
    load()
  }, [])

  const reveal = async (id: string) => {
    const { data } = await investorsApi.bankDetails(id)
    setBank((b) => ({ ...b, [id]: data }))
  }

  const blocked = (rows ?? []).filter((r) => r.kyc_status !== 'accepted').length

  return (
    <>
      <PageHeader
        title={t('investors.title')}
        subtitle={t('investors.subtitle')}
        actions={
          !creating ? (
            <Button size="sm" onClick={() => setCreating(true)}>
              <Plus size={15} /> {t('common.add')}
            </Button>
          ) : undefined
        }
      />

      {creating && (
        <div className="mb-6">
          <NewInvestor onCancel={() => setCreating(false)} onDone={() => { setCreating(false); load() }} />
        </div>
      )}

      <Allowance quota={quota} />

      {blocked > 0 && (
        <div className="mb-6">
          <Notice tone="warn" title={t('investors.blockedTitle', { count: blocked })}>
            {t('investors.blockedBody')}
          </Notice>
        </div>
      )}

      {rows === null ? (
        <Loading label={t('common.loading')} />
      ) : rows.length === 0 ? (
        <Card>
          <EmptyState title={t('investors.none')} icon={<Users size={32} />}>
            {t('investors.noneBody')}
          </EmptyState>
        </Card>
      ) : (
        <TableWrap>
          <thead>
            <tr>
              <Th>{t('common.investor')}</Th>
              <Th>{t('investors.kind')}</Th>
              <Th>{t('investors.verification')}</Th>
              <Th>{t('investors.reviewBy')}</Th>
              <Th>{t('investors.category')}</Th>
              <Th>{t('kyc.verdict')}</Th>
              <Th>{t('investors.bankDetails')}</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const k = KYC[r.kyc_status] ?? { tone: 'neutral' as const, icon: ShieldQuestion }
              const Icon = k.icon
              return (
                <tr key={r.id}>
                  <Td>
                    <span className="text-gray-900">{r.display_name}</span>
                    {r.email && <p className="mt-0.5 text-xs text-gray-500">{r.email}</p>}
                  </Td>
                  <Td className="text-gray-600">
                    {t(r.kind === 'societe' ? 'investors.company' : 'investors.person')}
                    {r.country_code && <span className="ml-1.5 text-gray-400">{r.country_code}</span>}
                  </Td>
                  <Td>
                    <Pill tone={k.tone}>
                      <Icon size={11} /> {t(`investors.kyc.${r.kyc_status}`, { defaultValue: r.kyc_status })}
                    </Pill>
                  </Td>
                  <Td className="text-gray-500 whitespace-nowrap">{day(r.kyc_review_due_on)}</Td>
                  {/* 🔴 « NON ÉVALUÉ » N'EST PAS UN BLANC : c'est l'état qui REFUSE tout
                      engagement, parce qu'une catégorie absente est lue comme protégée.
                      L'afficher comme une case vide laisserait croire à un détail. */}
                  <Td>
                    <button
                      type="button"
                      onClick={() => setAssessing(assessing?.id === r.id ? null : r)}
                      className="text-left"
                    >
                      {r.category ? (
                        <Pill tone={r.category === 'retail' ? 'info' : 'neutral'}>
                          {t(`investors.categories.${r.category}`)}
                        </Pill>
                      ) : (
                        <Pill tone="warn">{t('investors.notAssessed')}</Pill>
                      )}
                    </button>
                  </Td>
                  <Td>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => setDeciding(deciding?.id === r.id ? null : r)}
                    >
                      {t('kyc.decide')}
                    </Button>
                  </Td>
                  <Td>
                    {/* 🔴 THE IBAN IS NOT IN THE LISTING. A register is read constantly, and
                        shipping everybody's account details on every page view is how a
                        leak becomes exhaustive. One investor at a time, on demand. */}
                    {!r.has_bank_details ? (
                      <span className="text-gray-400 text-xs">{t('common.none')}</span>
                    ) : bank[r.id] ? (
                      <span className="font-mono text-xs">{bank[r.id].iban ?? '-'}</span>
                    ) : (
                      <button
                        onClick={() => reveal(r.id)}
                        className="inline-flex items-center gap-1 text-xs text-brand-navy hover:underline"
                      >
                        <Eye size={12} /> {t('common.show')}
                      </button>
                    )}
                  </Td>
                </tr>
              )
            })}
          </tbody>
        </TableWrap>
      )}

      {assessing && (
        <div className="mt-3">
          <Eligibility
            investor={assessing}
            onCancel={() => setAssessing(null)}
            onDone={() => {
              setAssessing(null)
              load()
            }}
          />
        </div>
      )}

      {deciding && (
        <div className="mt-3">
          <KycVerdict
            investor={deciding}
            onCancel={() => setDeciding(null)}
            onDone={() => {
              setDeciding(null)
              load()
            }}
          />
        </div>
      )}
    </>
  )
}


/**
 * Where the register stands against the plan, above the register itself.
 *
 * 🔴 IT SAYS NOTHING WHEN THERE IS NOTHING TO SAY. A fund with no console, or on an
 * unlimited plan, has no ceiling: a permanent « 12 / unlimited » strip would be furniture
 * the reader learns to skip, and the day it turns into a warning nobody would notice.
 *
 * ⚠️ « unknown » GETS ITS OWN SENTENCE, and it is the reason this component exists rather
 * than a number in the header. The console did not answer: the allowance cannot be read
 * and the next registration WILL be refused. Showing room to spare there, or showing
 * nothing at all, would leave a manager meeting a refusal with no idea why.
 */
function Allowance({ quota }: { quota: InvestorQuota | null }) {
  const { t } = useTranslation()
  if (!quota) return null

  if (quota.verdict === 'unknown') {
    return (
      <div className="mb-6">
        <Notice tone="warn" title={t('investors.quotaUnknownTitle')}>
          {t('investors.quotaUnknownBody')}
        </Notice>
      </div>
    )
  }
  if (quota.limit === null) return null

  const left = quota.limit - quota.current
  //   Quiet until it matters: the last two places, or past the ceiling.
  if (quota.verdict === 'ok' && left > 2) return null

  return (
    <div className="mb-6">
      <Notice
        tone={quota.verdict === 'blocked' ? 'bad' : 'warn'}
        title={t('investors.quotaTitle', { current: quota.current, limit: quota.limit })}
      >
        {quota.verdict === 'blocked'
          ? t('investors.quotaBlockedBody')
          : quota.verdict === 'overage'
            ? t('investors.quotaOverageBody', { price: quota.price })
            : t('investors.quotaNearBody', { count: left })}
      </Notice>
    </div>
  )
}

/**
 * Rendre un verdict — l'écran sans lequel le registre ne servait à rien.
 *
 * 🔴 UN VERDICT QUI N'EST PAS « ACCEPTÉ » BLOQUE L'ARGENT, et c'est écrit sur l'écran. Le
 * contrôle existait côté serveur depuis le premier jour ; sans ce formulaire, personne ne
 * pouvait accepter un investisseur, donc aucun engagement ni aucun encaissement n'était
 * possible. Un contrôle qu'on ne peut pas lever n'est pas prudent, il est mort.
 *
 * ⚠️ UN REFUS SANS MOTIF EST REFUSÉ ICI AUSSI, pas seulement par l'API. L'investisseur à
 * qui on dit « non » sans raison ne peut ni corriger son dossier ni demander à le revoir.
 */
function KycVerdict({
  investor, onCancel, onDone,
}: { investor: Row; onCancel: () => void; onDone: () => void }) {
  const { t } = useTranslation()
  const [status, setStatus] = useState(investor.kyc_status)
  const [risk, setRisk] = useState('standard')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  const needsReason = status === 'refused' || status === 'review'

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (needsReason && !reason.trim()) {
      toast.error(t('kyc.reasonRequired'))
      return
    }
    setBusy(true)
    try {
      // 🔴 THE SECOND DOOR THE ALLOWANCE IS COUNTED THROUGH. A refused file is not billed;
      // lifting that refusal makes it billable again, so this verdict can cost money even
      // though nothing on this form mentions a plan. The server asks, and this answers.
      const recorded = await withOverageConsent((acceptOverage) =>
        investorsApi.setKyc(investor.id, {
          status,
          risk_level: risk,
          reason: reason.trim() || undefined,
        }, acceptOverage),
      )
      if (!recorded) return
      toast.success(t('kyc.recorded'))
      onDone()
    } catch {
      /* handled by the interceptor */
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="p-4 border-brand-navy/30">
      <p className="text-sm font-semibold text-gray-900">
        {t('kyc.title', { name: investor.display_name })}
      </p>
      <p className="mt-0.5 mb-3 text-xs text-gray-500 max-w-2xl">{t('kyc.blocksMoney')}</p>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-4 items-end">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">{t('kyc.verdict')}</label>
          <Select
            value={status}
            onChange={setStatus}
            options={['accepted', 'pending', 'review', 'refused'].map((v) => ({
              value: v,
              label: t(`investors.kyc.${v}`),
            }))}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">{t('kyc.risk')}</label>
          <Select
            value={risk}
            onChange={setRisk}
            options={[
              { value: 'standard', label: t('kyc.riskStandard') },
              { value: 'high', label: t('kyc.riskHigh') },
            ]}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white"
          />
        </div>
        <Input
          label={t('kyc.reason')}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          required={needsReason}
        />
        <div className="flex gap-2">
          <Button type="submit" isLoading={busy}>{t('common.confirm')}</Button>
          <Button type="button" variant="ghost" onClick={onCancel}>{t('common.cancel')}</Button>
        </div>
      </form>
      <p className="mt-3 text-xs text-gray-500 max-w-3xl leading-relaxed">{needsReason ? t('kyc.reasonRequired') : undefined}</p>
    </Card>
  )
}

function NewInvestor({ onCancel, onDone }: { onCancel: () => void; onDone: () => void }) {
  const { t } = useTranslation()
  // ⚠️ 'personne' / 'societe' ARE THE STORED VALUES, and they stay French deliberately:
  // Le Comptoir Immo stores exactly these two on its landlords, and an investor is very
  // often a landlord. What is displayed goes through the catalogue.
  const [kind, setKind] = useState('personne')
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [company, setCompany] = useState('')
  const [email, setEmail] = useState('')
  const [iban, setIban] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      // ⚠️ `null` MEANS THE USER DECLINED THE SUPPLEMENT, which is neither a success nor a
      // failure. Announcing « added » here would name something that did not happen, and
      // the form must stay open so they can change their mind or their plan.
      const created = await withOverageConsent((acceptOverage) =>
        investorsApi.create({
          kind,
          first_name: kind === 'personne' ? firstName.trim() || null : null,
          last_name: kind === 'personne' ? lastName.trim() || null : null,
          company_name: kind === 'societe' ? company.trim() || null : null,
          email: email.trim() || null,
          iban: iban.trim() || null,
        }, acceptOverage),
      )
      if (!created) return
      toast.success(t('investors.added'))
      onDone()
    } catch {
      /* handled by the interceptor */
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="p-4">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-3">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">{t('investors.kind')}</label>
          <Select
            value={kind}
            onChange={setKind}
            options={[
              { value: 'personne', label: t('investors.person') },
              { value: 'societe', label: t('investors.company') },
            ]}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white"
          />
        </div>
        {kind === 'personne' ? (
          <>
            <Input label={t('investors.firstName')} value={firstName} onChange={(e) => setFirstName(e.target.value)} />
            <Input label={t('investors.lastName')} value={lastName} onChange={(e) => setLastName(e.target.value)} required />
          </>
        ) : (
          <div className="sm:col-span-2">
            <Input label={t('investors.companyName')} value={company} onChange={(e) => setCompany(e.target.value)} required />
          </div>
        )}
        <Input label={t('login.email')} type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <div className="sm:col-span-2">
          <Input
            label={t('investors.iban')}
            value={iban}
            onChange={(e) => setIban(e.target.value)}
            hint={t('investors.ibanHint')}
          />
        </div>
        <div className="sm:col-span-3 flex gap-2">
          <Button type="submit" isLoading={busy}>{t('common.add')}</Button>
          <Button type="button" variant="ghost" onClick={onCancel}>{t('common.cancel')}</Button>
        </div>
      </form>
    </Card>
  )
}


/**
 * Which protections apply to this investor, and on what declared basis.
 *
 * 🔴 SÉPARÉ DU VERDICT KYC, ET C'EST LE SUJET. Le KYC dit si le fonds peut traiter avec
 * cette personne ; ceci dit combien elle peut engager avant qu'un avertissement soit dû.
 * Les réunir dans un même écran laisserait un clic « accepté » lever un plafond au passage.
 *
 * ⚠️ UNE CAPACITÉ REMISE À VIDE REND LE REFUS, et c'est voulu : oublier ce que quelqu'un a
 * déclaré doit ramener le fonds à « nous ne savons pas », jamais à « pas de plafond ».
 */
function Eligibility({
  investor, onCancel, onDone,
}: { investor: Row; onCancel: () => void; onDone: () => void }) {
  const { t } = useTranslation()
  const [category, setCategory] = useState<InvestorCategory>(investor.category ?? 'retail')
  const [capacity, setCapacity] = useState(investor.loss_bearing_capacity ?? '')
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await investorsApi.setEligibility(investor.id, {
        category,
        loss_bearing_capacity: capacity.trim() || null,
      })
      toast.success(t('investors.eligibilityRecorded'))
      onDone()
    } catch {
      /* handled by the interceptor */
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="p-4 border-brand-navy/30">
      <p className="text-sm font-semibold text-gray-900">
        {t('investors.assessTitle', { name: investor.display_name })}
      </p>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-3 items-end mt-3">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('investors.category')}
          </label>
          <Select
            value={category}
            onChange={(v) => setCategory(v as InvestorCategory)}
            options={(['retail', 'sophisticated', 'professional'] as InvestorCategory[]).map((c) => ({
              value: c,
              label: t(`investors.categories.${c}`),
            }))}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white"
          />
        </div>
        <Input
          label={t('investors.capacity')}
          type="number"
          min="0"
          step="0.01"
          value={capacity}
          onChange={(e) => setCapacity(e.target.value)}
        />
        <div className="flex gap-2">
          <Button type="submit" disabled={busy}>{t('common.confirm')}</Button>
          <Button type="button" variant="secondary" onClick={onCancel}>{t('common.cancel')}</Button>
        </div>
      </form>
      {/* L'aide vit SOUS la rangée, jamais dans une cellule alignée en bas. */}
      <p className="mt-2 text-xs text-gray-500 max-w-3xl">{t('investors.capacityHint')}</p>
    </Card>
  )
}
