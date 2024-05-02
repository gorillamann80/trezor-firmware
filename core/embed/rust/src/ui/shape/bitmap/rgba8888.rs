use super::{Bitmap, BitmapFormat, BitmapView};
use crate::{
    trezorhal::bitblt::BitBlt,
    ui::{display::Color, geometry::Rect},
};

impl<'a> Bitmap<'a> {
    /// Fills a rectangle with the specified color.
    ///
    /// The function is aplicable only on bitmaps with RGBA888 format.
    pub fn rgba8888_fill(&mut self, r: Rect, clip: Rect, color: Color, alpha: u8) {
        assert!(self.format() == BitmapFormat::RGBA8888);
        if let Some(bitblt) = BitBlt::new_fill(r, clip, color, alpha) {
            let bitblt = bitblt.with_dst(self);
            unsafe { bitblt.rgba8888_fill() };
            self.mark_dma_pending();
        }
    }

    pub fn rgba8888_copy(&mut self, r: Rect, clip: Rect, src: &BitmapView) {
        assert!(self.format() == BitmapFormat::RGBA8888);
        if let Some(bitblt) = BitBlt::new_copy(r, clip, src) {
            let bitblt = bitblt.with_dst(self);
            match src.format() {
                BitmapFormat::MONO4 => unsafe { bitblt.rgba8888_copy_mono4() },
                BitmapFormat::RGB565 => unsafe { bitblt.rgba8888_copy_rgb565() },
                BitmapFormat::RGBA8888 => unsafe { bitblt.rgba8888_copy_rgba8888() },
                _ => panic!("Unsupported DMA operation"),
            }
            self.mark_dma_pending();
            src.bitmap.mark_dma_pending();
        }
    }

    pub fn rgba8888_blend(&mut self, r: Rect, clip: Rect, src: &BitmapView) {
        assert!(self.format() == BitmapFormat::RGBA8888);
        if let Some(bitblt) = BitBlt::new_copy(r, clip, src) {
            let bitblt = bitblt.with_dst(self);
            match src.format() {
                BitmapFormat::MONO4 => unsafe { bitblt.rgba8888_blend_mono4() },
                _ => panic!("Unsupported DMA operation"),
            }
            self.mark_dma_pending();
            src.bitmap.mark_dma_pending();
        }
    }
}