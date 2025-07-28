"use client";
import { TLBaseShape } from 'tldraw'
import { ProductTypes } from '@/types/product'

export type StickerPriority = 'alta' | 'media' | 'baja' | 'ninguna'

export type StickerShape = TLBaseShape<
  'sticker',
  {
    grid: string
    content: string
  }
> & {
  x: number
  y: number
  rotation: number
  index: string
}