import { create } from 'zustand'
import { api } from '../api/client'

interface DramaState {
  currentId: string | null
  data: any
  polling: boolean
  storyConfirmed: boolean
  mergeSelected: number[]
  startDrama: (params: any) => Promise<void>
  stopDrama: () => Promise<void>
  pollStatus: () => Promise<void>
  setStoryConfirmed: (v: boolean) => void
  setMergeSelected: (v: number[]) => void
  clearMergeSelection: () => void
  restore: (dramaId: string) => void
  clear: () => void
}

export const useDramaStore = create<DramaState>((set, get) => ({
  currentId: null,
  data: null,
  polling: false,
  storyConfirmed: false,
  mergeSelected: [],

  startDrama: async (params) => {
    const res = await api.startDrama(params)
    set({ currentId: res.drama_id, polling: true })
    localStorage.setItem('currentDramaId', res.drama_id)
  },

  stopDrama: async () => {
    const id = get().currentId
    if (!id) return
    await api.stopDrama(id)
    set({ polling: false })
  },

  pollStatus: async () => {
    const id = get().currentId
    if (!id) return
    try {
      const res = await api.dramaStatus(id)
      set({ data: res })
      if (['completed', 'failed'].includes(res.status)) {
        set({ polling: false })
        localStorage.removeItem('currentDramaId')
      }
    } catch { /* ignore */ }
  },

  setStoryConfirmed: (v) => set({ storyConfirmed: v }),
  setMergeSelected: (v) => set({ mergeSelected: v }),
  clearMergeSelection: () => set({ mergeSelected: [] }),
  restore: (dramaId) => set({ currentId: dramaId, polling: true }),
  clear: () => set({ currentId: null, data: null, polling: false, storyConfirmed: false, mergeSelected: [] }),
}))