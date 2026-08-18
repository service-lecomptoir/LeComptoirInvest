import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Eye, Plus, ShieldAlert, ShieldCheck, ShieldQuestion, ShieldX, Users } from 'lucide-react'
import { investorsApi } from '@/api'
import { Button, Input, Select } from '@/components/ui'
import {
  Card, EmptyState, Loading, Notice, PageHeader, Pill, TableWrap, Td, Th,
} from '@/components/common/Primitives'
import { day } from '@/lib/format'
import { toast } from '@/store/toast'

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
}

export default function Investors() {
  const { t } = useTranslation()
  const [rows, setRows] = useState<Row[] | null>(null)
  const [creating, setCreating] = useState(false)
  const [deciding, setDeciding] = useState<Row | null>(null)
  const [bank, setBank] = useState<Record<string, { iban: string | null }>>({})

  const load = () =>
    investorsApi.list().then((r) => setRows(r.data as unknown as Row[])).catch(() => setRows([]))
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
      await investorsApi.setKyc(investor.id, {
        status,
        risk_level: risk,
        reason: reason.trim() || undefined,
      })
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
      await investorsApi.create({
        kind,
        first_name: kind === 'personne' ? firstName.trim() || null : null,
        last_name: kind === 'personne' ? lastName.trim() || null : null,
        company_name: kind === 'societe' ? company.trim() || null : null,
        email: email.trim() || null,
        iban: iban.trim() || null,
      })
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
