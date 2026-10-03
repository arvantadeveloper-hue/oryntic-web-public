import React, { useState } from "react";
import { Images } from "lucide-react";
import { GalleryGrid, GalleryFilterBar, GallerySearch } from "../components/Gallery";
import { PreviewDrawer, ShareModal } from "../components/GalleryPreview";

export default function Gallery() {
  const [type, setType] = useState("all");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(null);
  const [share, setShare] = useState(null);
  return (
    <div className="mx-auto max-w-6xl p-5 sm:p-8 fade-up" data-testid="gallery-page">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-slate-900 sm:text-3xl"><Images size={26} className="text-[#2F6BFF]" /> Galeri</h1>
          <p className="mt-1 text-sm text-slate-500">Semua dokumen, gambar, dan video yang dibuat asisten Anda. Klik kartu untuk pratinjau; unduh, bagikan, atau lampirkan kembali ke chat.</p>
        </div>
        <div className="flex flex-wrap items-center gap-3"><GallerySearch value={q} onChange={setQ} /><GalleryFilterBar value={type} onChange={setType} /></div>
      </div>
      <div className="mt-6"><GalleryGrid type={type} q={q} onOpen={setOpen} onShare={setShare} /></div>
      <PreviewDrawer item={open} onClose={() => setOpen(null)} />
      {share && <ShareModal item={share} onClose={() => setShare(null)} />}
    </div>
  );
}
