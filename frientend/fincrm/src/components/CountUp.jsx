import { useEffect, useMemo, useState, useSyncExternalStore } from 'react'

const motionQuery = () => window.matchMedia('(prefers-reduced-motion: reduce)')
const subscribeToMotionPreference = (onChange) => {
  const query = motionQuery()
  query.addEventListener('change', onChange)
  return () => query.removeEventListener('change', onChange)
}
const getReducedMotion = () => motionQuery().matches

export default function CountUp({ value, duration = 900 }) {
  const parts = useMemo(() => {
    const source = String(value ?? 0)
    const match = source.match(/-?[\d,]+(?:\.\d+)?/)
    if (!match) return { target: 0, prefix: '', suffix: source }
    return {
      target: Number(match[0].replaceAll(',', '')) || 0,
      prefix: source.slice(0, match.index),
      suffix: source.slice(match.index + match[0].length),
      decimals: (match[0].split('.')[1] || '').length,
    }
  }, [value])
  const [current, setCurrent] = useState(0)
  const reduceMotion = useSyncExternalStore(subscribeToMotionPreference, getReducedMotion, () => true)

  useEffect(() => {
    if (reduceMotion || !Number.isFinite(parts.target)) return undefined
    let frame
    let start
    const animate = (time) => {
      if (start === undefined) start = time
      const progress = Math.min(1, (time - start) / duration)
      const eased = 1 - (1 - progress) ** 3
      setCurrent(parts.target * eased)
      if (progress < 1) frame = requestAnimationFrame(animate)
    }
    frame = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(frame)
  }, [parts.target, duration, reduceMotion])

  const displayValue = reduceMotion ? parts.target : current

  const formatted = new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: parts.decimals || 0,
    maximumFractionDigits: parts.decimals || 0,
  }).format(displayValue)
  return <span aria-label={`${parts.prefix}${new Intl.NumberFormat('en-IN', { maximumFractionDigits: parts.decimals || 0 }).format(parts.target)}${parts.suffix}`}>
    {parts.prefix}{formatted}{parts.suffix}
  </span>
}
