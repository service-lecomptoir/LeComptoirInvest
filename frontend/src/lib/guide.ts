import type { LucideIcon } from 'lucide-react'
import {
  AlarmClock,
  Banknote,
  Building2,
  CreditCard,
  FileText,
  Layers,
  LayoutDashboard,
  PieChart,
  Receipt,
  TrendingUp,
  UserRound,
  Users,
  Wallet,
} from 'lucide-react'

/**
 * The user guide: one card per screen of the product, like the other products of the
 * house (the manager, 27 Sept 2026). Le Comptoir RH shows a card per screen with a vignette.
 *
 * 🔴 TWO AUDIENCES, TWO GUIDES IN ONE. The fund and the investor do not have the same
 * screens, and `/` or `/projects` are not the same screen for both: a guide describing the
 * fund's register to an investor would send them looking for a menu they do not have. So
 * a card says whom it is for, from the same flag the menu uses (`seesWholeFund`).
 *
 * 🔴 THE CARD'S TITLE IS THE SCREEN'S OWN LABEL, never a second wording: the menu reads
 * `nav.treasury`, so does the card.
 *
 * ⚠️ `route` IS THE ROUTER'S PATH, WRITTEN AS THE ROUTER WRITES IT. The guard
 * `guideCoversEveryScreen.test.ts` reads every path of `router.tsx` and demands a card
 * here: a screen added without its card fails the build rather than arriving mute.
 */
export type Audience = 'fund' | 'investor'

export interface GuideCard {
  /** The path, exactly as `router.tsx` declares it. */
  route: string
  /** The card's text lives under `guide.cards.<id>.what` and `.how`. */
  id: string
  /** The catalogue key of the screen's own label (menu entry). */
  title: string
  icon: LucideIcon
  /** Whom the card is for; absent, every account. */
  audience?: Audience
}

export interface GuideSection {
  key: string
  cards: GuideCard[]
}

export const GUIDE_SECTIONS: GuideSection[] = [
  {
    key: 'guide.sections.fund',
    cards: [
      { route: '/', id: 'dashboard', title: 'nav.dashboard', icon: LayoutDashboard, audience: 'fund' },
      { route: '/projects', id: 'projects', title: 'nav.projects', icon: Building2, audience: 'fund' },
      { route: '/funds', id: 'funds', title: 'nav.funds', icon: Layers, audience: 'fund' },
      { route: '/distributions', id: 'distributions', title: 'nav.distributions', icon: Banknote, audience: 'fund' },
      { route: '/performance', id: 'performance', title: 'nav.performance', icon: TrendingUp, audience: 'fund' },
      { route: '/treasury', id: 'treasury', title: 'nav.treasury', icon: Wallet, audience: 'fund' },
      { route: '/late-calls', id: 'lateCalls', title: 'nav.lateCalls', icon: AlarmClock, audience: 'fund' },
    ],
  },
  {
    key: 'guide.sections.investors',
    cards: [
      { route: '/investors', id: 'investors', title: 'nav.register', icon: Users, audience: 'fund' },
      { route: '/subscriptions', id: 'subscriptions', title: 'nav.subscriptions', icon: Receipt, audience: 'fund' },
    ],
  },
  {
    key: 'guide.sections.mySpace',
    cards: [
      { route: '/', id: 'portfolio', title: 'nav.myPortfolio', icon: PieChart, audience: 'investor' },
      { route: '/capital-calls', id: 'capitalCalls', title: 'nav.myCalls', icon: Wallet, audience: 'investor' },
      { route: '/my-distributions', id: 'myDistributions', title: 'nav.myDistributions', icon: Banknote, audience: 'investor' },
      { route: '/statement', id: 'statement', title: 'nav.statement', icon: FileText, audience: 'investor' },
      { route: '/projects', id: 'theProjects', title: 'nav.theProjects', icon: Building2, audience: 'investor' },
    ],
  },
  {
    key: 'guide.sections.account',
    cards: [
      { route: '/profile', id: 'profile', title: 'profile.title', icon: UserRound },
      { route: '/billing', id: 'billing', title: 'nav.billing', icon: CreditCard, audience: 'fund' },
    ],
  },
]

/** The route of the guide itself: the one screen that needs no card. */
export const GUIDE_ROUTE = '/guide'
