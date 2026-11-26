import { useLayoutEffect, useState } from 'react'

export default function useSidePanelEntrance(dialogRef, active = true) {
  const [entered, setEntered] = useState(false)

  useLayoutEffect(() => {
    const dialog = dialogRef?.current
    if (!active || (dialogRef && !dialog)) {
      setEntered(false)
      return undefined
    }

    if (dialog && !dialog.open) dialog.showModal()
    setEntered(false)

    let secondFrame = 0
    const firstFrame = requestAnimationFrame(() => {
      secondFrame = requestAnimationFrame(() => setEntered(true))
    })

    return () => {
      cancelAnimationFrame(firstFrame)
      cancelAnimationFrame(secondFrame)
      if (dialog?.open) dialog.close()
    }
  }, [active, dialogRef])

  return entered
}
