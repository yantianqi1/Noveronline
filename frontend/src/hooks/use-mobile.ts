import * as React from "react"

const MOBILE_BREAKPOINT = 768
const TABLET_BREAKPOINT = 980
const DESKTOP_BREAKPOINT = 1180

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = React.useState(false)

  React.useEffect(() => {
    const mql = window.matchMedia(query)
    const onChange = () => setMatches(mql.matches)
    mql.addEventListener("change", onChange)
    setMatches(mql.matches)
    return () => mql.removeEventListener("change", onChange)
  }, [query])

  return matches
}

export function useIsMobile() {
  return useMediaQuery(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`)
}

/** True when viewport < 980px (sidebar should auto-collapse). */
export function useIsTablet() {
  return useMediaQuery(`(max-width: ${TABLET_BREAKPOINT - 1}px)`)
}

/** True when viewport >= 1180px (workbench can use wider grid). */
export function useIsWideDesktop() {
  return useMediaQuery(`(min-width: ${DESKTOP_BREAKPOINT}px)`)
}
