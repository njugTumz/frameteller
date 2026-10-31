import { create } from 'zustand'

/** "Report a problem" asked for from outside the studio's form (the phone header menu): the form opens. */
export const useReportRequests = create<{ asked: number }>(() => ({ asked: 0 }))

export const requestReport = () => useReportRequests.setState((s) => ({ asked: s.asked + 1 }))
