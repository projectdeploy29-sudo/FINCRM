import { useEffect, useRef, useState } from 'react'
import logoUrl from '../assets/logo.jpg'
import dashboardImage from '../assets/features/dashboard.jpeg'
import pipelineImage from '../assets/features/pipeline.png'
import reportsImage from '../assets/features/Reports.png'
import assistantImage from '../assets/features/AI Assistent.png'
import featuresImage from '../assets/features/key features.png'
import PlanCatalog from './PlanCatalog'
import './LandingPage.css'

const features = [
  {
    icon: '↗',
    title: 'Move leads forward',
    description: 'See every lead by stage, keep ownership clear, and follow progress through the lending journey.',
    tone: 'red',
  },
  {
    icon: '◷',
    title: 'Keep follow-ups on track',
    description: 'Bring today’s tasks and customer conversations together so the next step is easy to find.',
    tone: 'blue',
  },
  {
    icon: '▥',
    title: 'Understand the work',
    description: 'Review pipeline, payment activity, and team performance from clear reports and summaries.',
    tone: 'green',
  },
]

const productFeatures = [
  { title: 'Dashboard overview', description: 'See the work that needs attention, key activity, and pipeline health as soon as you sign in.', image: dashboardImage, tag: '01 · OVERVIEW' },
  { title: 'Lead pipeline', description: 'Move opportunities through clear stages and keep ownership and next steps visible.', image: pipelineImage, tag: '02 · PIPELINE' },
  { title: 'Reports that clarify', description: 'Turn lending activity into useful summaries that help your team make informed decisions.', image: reportsImage, tag: '03 · REPORTING' },
  { title: 'AI assistant', description: 'Get a helping hand finding insights and navigating your finance workspace.', image: assistantImage, tag: '04 · ASSISTANCE' },
  { title: 'Connected CRM tools', description: 'Bring your everyday customer and team workflows together in one workspace.', image: featuresImage, tag: '05 · WORKSPACE' },
]

const sidebarOptions = [
  ['Dashboard', 'A quick view of work, activity, and key numbers.'],
  ['Records', 'Open organized records for managers, teams, employees, customers, leads, payments, and organization hierarchy.'],
  ['Send', 'Coordinate messages and customer communication.'],
  ['Follow-ups', 'Plan and track the next conversation.'],
  ['Today', 'Focus on tasks and follow-ups due now.'],
  ['Pipeline', 'See lead progress from first contact to completion.'],
  ['Report', 'Review team activity and lending performance.'],
  ['Settings', 'Manage your profile and workspace preferences.'],
  ['My subscription', 'Review your organization’s current plan and subscription.'],
  ['Billing history', 'Review payments, invoices, and subscription billing history.'],
  ['Plans', 'Compare plans available for your organization.'],
]

function CheckIcon() {
  return <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m4 10.5 4 4L16.5 6" /></svg>
}

function ProductPreview() {
  return <div className="landing-preview-wrap" aria-label="Illustration of the Auron FIN CRM workspace">
    <div className="landing-preview-glow" />
    <div className="landing-preview-card">
      <header className="preview-topbar">
        <div className="preview-brand"><img src={logoUrl} alt="" /><b>AURON FIN CRM</b></div>
        <span className="preview-period"><i /> Workspace overview</span>
        <span className="preview-avatar">A</span>
      </header>
      <div className="preview-content">
        <div className="preview-welcome"><div><span>YOUR FINANCE WORKSPACE</span><h2>Good morning, Aarav</h2><p>A clear view of what needs attention.</p></div><span className="preview-date">Today <b>⌄</b></span></div>
        <div className="preview-metrics">
          <article><span>Active leads</span><strong>— —</strong><i className="preview-metric-line red-line" /></article>
          <article><span>Follow-ups due</span><strong>— —</strong><i className="preview-metric-line blue-line" /></article>
          <article><span>Payments</span><strong>— —</strong><i className="preview-metric-line green-line" /></article>
        </div>
        <section className="preview-pipeline">
          <div className="preview-section-title"><div><b>Lead pipeline</b><small>Track progress across stages</small></div><span>View pipeline ↗</span></div>
          <div className="preview-stage-list">
            <div><span className="stage-dot stage-red" /><span>New</span><i><b style={{ width: '78%' }} /></i></div>
            <div><span className="stage-dot stage-blue" /><span>Contacted</span><i><b style={{ width: '58%' }} /></i></div>
            <div><span className="stage-dot stage-green" /><span>Approved</span><i><b style={{ width: '36%' }} /></i></div>
          </div>
        </section>
        <section className="preview-followup">
          <span className="preview-followup-icon">✓</span><div><b>Today’s priorities</b><small>Tasks and follow-ups in one place</small></div><span className="preview-followup-arrow">→</span>
        </section>
      </div>
      <span className="preview-caption">Illustrative workspace preview</span>
    </div>
    <div className="preview-float-card"><span className="preview-float-icon"><CheckIcon /></span><span><b>Next step, made clear</b><small>Keep every conversation moving</small></span></div>
  </div>
}

export default function LandingPage({ onNavigate }) {
  const [activeFeature, setActiveFeature] = useState(0)
  const [orbitOpen, setOrbitOpen] = useState(false)
  const sidebarTourRef = useRef(null)
  useEffect(() => {
    const section = sidebarTourRef.current
    if (!section || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        section.classList.add('is-visible')
        observer.disconnect()
      }
    }, { threshold: 0.16 })
    observer.observe(section)
    return () => observer.disconnect()
  }, [])
  return <main className="public-home">
    <section className="landing-hero">
      <div className="landing-hero-copy">
        <p className="landing-eyebrow"><span /> FINANCE WORKFLOWS, CONNECTED</p>
        <h1>Bring every lending relationship into <em>focus.</em></h1>
        <p className="landing-lede">Auron FIN CRM helps your team manage leads, customer follow-ups, repayment activity, and performance from one organized workspace.</p>
        <div className="landing-hero-actions">
          <button type="button" className="landing-primary" onClick={() => onNavigate('plans')}>Explore plans <span>↗</span></button>
          <button type="button" className="landing-secondary" onClick={() => onNavigate('login')}>Sign in to Auron FIN CRM</button>
        </div>
        <div className="landing-trust-line"><span><CheckIcon /> Clear ownership</span><i /><span><CheckIcon /> Practical follow-ups</span><i /><span><CheckIcon /> Useful reporting</span></div>
      </div>
      <ProductPreview />
    </section>

    <section className="landing-capabilities" id="features">
      <div className="landing-section-heading"><p className="landing-eyebrow">BUILT AROUND YOUR WORK</p><h2>From first conversation to confident decisions.</h2><p>Keep the details connected, so your team can spend less time searching and more time moving work forward.</p></div>
      <div className="landing-feature-grid">{features.map((feature, index) => <article className="landing-feature-card" key={feature.title}>
        <span className={`landing-feature-icon ${feature.tone}`}>{feature.icon}</span><span className="landing-feature-number">0{index + 1}</span>
        <h3>{feature.title}</h3><p>{feature.description}</p><span className="landing-feature-rule" />
      </article>)}</div>
    </section>

    <section className="landing-showcase" aria-labelledby="landing-showcase-title">
      <div className="landing-section-heading"><p className="landing-eyebrow">A CLOSER LOOK</p><h2 id="landing-showcase-title">Tools for the work behind every decision.</h2><p>Choose a feature to see how Auron FIN CRM brings your daily work into focus.</p></div>
      <div className={`feature-orbit${orbitOpen ? ' is-open' : ''}`}>
        <div className="feature-orbit-rings" aria-hidden="true"><i /><i /><i /></div>
        <button type="button" className="feature-orbit-core" aria-expanded={orbitOpen} aria-label={orbitOpen ? 'Hide workspace features' : 'Explore Auron FIN CRM features'} onClick={() => setOrbitOpen((open) => !open)}><span className="feature-orbit-core-glow" /><img src={logoUrl} alt="" /><strong>AURON<br />FIN CRM</strong><span className="feature-orbit-core-prompt">{orbitOpen ? 'Tap to close' : 'Explore features'}</span></button>
        <div className="feature-orbit-items">{sidebarOptions.map(([title, description], index) => <article className="feature-orbit-item" key={title} style={{ '--orbit-index': index, '--orbit-total': sidebarOptions.length, '--orbit-delay': `${index * 65}ms` }} tabIndex={orbitOpen ? 0 : -1} aria-label={`${title}: ${description}`}><span className="feature-orbit-dot" /><span className="feature-orbit-label">{title}</span><span className="feature-orbit-description">{description}</span></article>)}</div>
        <p className="feature-orbit-hint">{orbitOpen ? 'Hover or focus on any feature to see what it does' : 'Click to explore all workspace features'}</p>
      </div>
      <div className="showcase-layout">
        <div className="showcase-feature-list" role="tablist" aria-label="CRM features">
          {productFeatures.map((feature, index) => <button type="button" role="tab" aria-selected={activeFeature === index} aria-controls="showcase-preview" id={`showcase-tab-${index}`} className={`showcase-feature-button${activeFeature === index ? ' active' : ''}`} key={feature.title} onClick={() => setActiveFeature(index)}>
            <span className="showcase-feature-index">0{index + 1}</span><span className="showcase-feature-copy"><strong>{feature.title}</strong><small>{feature.description}</small></span><span className="showcase-feature-arrow" aria-hidden="true">↗</span>
          </button>)}
        </div>
        <div className="showcase-preview" id="showcase-preview" role="tabpanel" aria-labelledby={`showcase-tab-${activeFeature}`} key={activeFeature}>
          <div className="showcase-preview-top"><span>{productFeatures[activeFeature].tag}</span><i><b /> FEATURE PREVIEW</i></div>
          <div className="showcase-image-frame"><img src={productFeatures[activeFeature].image} alt={`${productFeatures[activeFeature].title} feature preview`} /></div>
          <div className="showcase-preview-caption"><strong>{productFeatures[activeFeature].title}</strong><span>Designed to keep your team moving.</span></div>
        </div>
      </div>
    </section>

    <section className="landing-sidebar-tour" aria-labelledby="sidebar-tour-title" ref={sidebarTourRef}>
      <div className="sidebar-tour-heading"><p className="landing-eyebrow">EVERYTHING IN ITS PLACE</p><h2 id="sidebar-tour-title">A clear path through your work.</h2><p>Each area of your workspace has a purpose. Follow the markers to see what your team can do.</p></div>
      <div className="sidebar-tour-list">{sidebarOptions.map(([title, description], index) => <article className="sidebar-tour-item" key={title} style={{ '--tour-delay': `${index * 150}ms` }}><span className="sidebar-tour-check"><CheckIcon /></span><span className="sidebar-tour-text"><strong>{title}</strong><small>{description}</small></span><span className="sidebar-tour-number">{String(index + 1).padStart(2, '0')}</span></article>)}</div>
    </section>

    <section className="landing-workflow">
      <div className="workflow-copy"><p className="landing-eyebrow">A CONNECTED WAY TO WORK</p><h2>Know what happened. Know what comes next.</h2><p>Auron FIN CRM brings the everyday pieces of lending operations into one view—from assigning leads to reviewing payment and follow-up activity.</p><button type="button" className="landing-text-link" onClick={() => onNavigate('plans')}>Find a plan for your team <span>→</span></button></div>
      <div className="workflow-steps" aria-label="Auron FIN CRM workflow">
        {[['01', 'Capture', 'Keep customer and lead records organized.'], ['02', 'Coordinate', 'Assign owners and plan the next follow-up.'], ['03', 'Review', 'See pipeline and payment activity in reports.']].map(([number, title, description], index) => <article className="workflow-step" key={number}>
          <span className="workflow-step-number">{number}</span><div className="workflow-step-copy"><b>{title}</b><p>{description}</p></div>{index < 2 && <span className="workflow-connector" aria-hidden="true">↓</span>}
        </article>)}
      </div>
    </section>

    <section className="landing-plans" id="plans" aria-labelledby="landing-plans-title">
      <div className="landing-section-heading">
        <p className="landing-eyebrow">PLANS FOR EVERY STAGE</p>
        <h2 id="landing-plans-title">The right workspace for your team.</h2>
        <p>Compare plans and choose the capacity that fits your organization.</p>
      </div>
      <PlanCatalog />
    </section>

    <section className="landing-bottom-cta">
      <div><p className="landing-eyebrow">YOUR TEAM’S NEXT STEP STARTS HERE</p><h2>Make the whole customer journey easier to see.</h2></div>
      <div><button type="button" className="landing-primary" onClick={() => onNavigate('plans')}>View plans <span>↗</span></button><button type="button" className="landing-cta-login" onClick={() => onNavigate('login')}>Already have an account? Sign in</button></div>
    </section>
    <footer className="landing-footer">
      <div className="landing-footer-main">
        <div className="landing-footer-brand"><img src={logoUrl} alt="" /><div><strong>AURON FIN CRM</strong><span>Customer and finance workflows, connected.</span></div></div>
        <div className="landing-footer-contact"><h3>Get in touch</h3><a href="mailto:contact@alphaauron.com"><span>General enquiries</span><strong>contact@alphaauron.com</strong></a><a href="mailto:ceo@alphaauron.com"><span>Founder &amp; CEO — M Kishore Kumar Naik</span><strong>ceo@alphaauron.com</strong></a><a href="tel:+916303059843"><span>Mobile</span><strong>+91 63030 59843</strong></a></div>
        <div className="landing-footer-address"><h3>Office</h3><address>28-39/6, First Floor, Punganur, 28th Block, Kothaindlu, Madanapalli Road, Chittoor District, Andhra Pradesh – 517247, India.</address><a href="https://alphaauron.com/" target="_blank" rel="noopener noreferrer">Visit Alpha Auron ↗</a></div>
      </div>
      <div className="landing-footer-bottom"><span>© {new Date().getFullYear()} Auron FIN CRM. All rights reserved.</span><span>Powered by <a href="https://alphaauron.com/" target="_blank" rel="noopener noreferrer">Alpha Auron</a></span><div><button type="button" onClick={() => onNavigate('plans')}>Plans</button><button type="button" onClick={() => onNavigate('login')}>Sign in</button><button type="button" onClick={() => onNavigate('privacy-policy')}>Privacy Policy</button></div></div>
    </footer>
  </main>
}
