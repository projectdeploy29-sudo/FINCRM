import { useEffect, useState } from 'react'
import logoUrl from '../assets/logo.jpg'
import './WebsiteIntro.css'

const introAreas = ['Leads', 'Follow-ups', 'Payments', 'Reports']

export default function WebsiteIntro({ onComplete }) {
  const [isExiting, setIsExiting] = useState(false)

  useEffect(() => {
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const exitTimer = window.setTimeout(() => setIsExiting(true), reducedMotion ? 250 : 2950)
    const finishTimer = window.setTimeout(onComplete, reducedMotion ? 650 : 3550)
    return () => {
      window.clearTimeout(exitTimer)
      window.clearTimeout(finishTimer)
    }
  }, [onComplete])

  return <div className={`website-intro${isExiting ? ' is-exiting' : ''}`} role="status" aria-live="polite" aria-label="Introducing Auron FIN CRM">
    <div className="website-intro-grid" />
    <span className="website-intro-sweep" />
    <div className="website-intro-orb website-intro-orb-one" />
    <div className="website-intro-orb website-intro-orb-two" />
    <div className="website-intro-content">
      <div className="website-intro-scene" aria-hidden="true">
        <span className="website-intro-ring website-intro-ring-outer" /><span className="website-intro-ring website-intro-ring-inner" />
        <span className="website-intro-axis website-intro-axis-x" /><span className="website-intro-axis website-intro-axis-y" />
        <div className="website-intro-mark"><span className="website-intro-mark-glow" /><img src={logoUrl} alt="" /><i /></div>
        <div className="website-intro-areas">{introAreas.map((area, index) => <span key={area} className={`intro-area intro-area-${index + 1}`} style={{ '--intro-index': index }}><i />{area}</span>)}</div>
      </div>
      <p className="website-intro-eyebrow">THE FINANCE WORKSPACE FOR WHAT’S NEXT</p>
      <h1><span>Every relationship.</span><strong>In <em>focus.</em></strong></h1>
      <p className="website-intro-tagline"><b>AURON FIN CRM</b><i /> A clearer path from first contact to confident decisions.</p>
      <div className="website-intro-loader" aria-hidden="true"><span /></div>
      <p className="website-intro-caption"><i /> CONNECTING YOUR WORKFLOW</p>
    </div>
    <span className="website-intro-footer">POWERED BY <strong>ALPHA AURON</strong></span>
  </div>
}
