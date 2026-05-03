import React, { useState, useRef, useEffect } from 'react';
import { Upload, FileText, MessageSquare, Smartphone, Image, CheckCircle, XCircle, Loader2, AlertTriangle, Clock } from 'lucide-react';
import { NeedAPI } from '../api/endpoints';
import { toast } from 'react-hot-toast';

type IngestionTab = 'mobile' | 'text' | 'csv' | 'image' | 'review';

const CATEGORIES = [
  'food', 'health', 'shelter', 'education', 'livelihood',
  'water', 'mental_health', 'legal', 'hygiene', 'other'
];

export function IngestionPage() {
  const [tab, setTab] = useState<IngestionTab>('mobile');

  return (
    <div className="flex flex-col h-full">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-headline font-semibold text-brand-900">Ingestion Pipeline</h2>
          <p className="text-sm text-gray-500 mt-1">Submit needs via mobile, text, CSV, or image.</p>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-2xl mb-6 w-fit">
        {([
          { id: 'mobile', label: 'Mobile', icon: Smartphone },
          { id: 'text', label: 'WhatsApp/SMS', icon: MessageSquare },
          { id: 'csv', label: 'CSV Upload', icon: FileText },
          { id: 'image', label: 'Image OCR', icon: Image },
          { id: 'review', label: 'Review Queue', icon: CheckCircle },
        ] as const).map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold transition-all ${
              tab === t.id ? 'bg-white text-brand-600 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            <t.icon className="w-4 h-4" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-auto">
        {tab === 'mobile' && <MobileIngestForm />}
        {tab === 'text' && <TextIngestForm />}
        {tab === 'csv' && <CsvIngestForm />}
        {tab === 'image' && <ImageIngestForm />}
        {tab === 'review' && <ReviewQueue />}
      </div>
    </div>
  );
}

// ── MOBILE INGEST FORM ──────────────────────────────────────
function MobileIngestForm() {
  const [category, setCategory] = useState('food');
  const [description, setDescription] = useState('');
  const [language, setLanguage] = useState('en');
  const [locationText, setLocationText] = useState('');
  const [lat, setLat] = useState<number | undefined>();
  const [lng, setLng] = useState<number | undefined>();
  const [beneficiaryCount, setBeneficiaryCount] = useState(1);
  const [householdId, setHouseholdId] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [lastResult, setLastResult] = useState<any>(null);

  const handleSubmit = async () => {
    if (!description) { toast.error('Description required'); return; }
    setIsSubmitting(true);
    try {
      const res = await NeedAPI.ingestMobile({
        category,
        description,
        location_text: locationText || undefined,
        latitude: lat,
        longitude: lng,
        beneficiary_count: beneficiaryCount,
        known_household_id: householdId || undefined,
        language,
        vulnerability_flags: {},
      });
      setLastResult(res.data);
      toast.success(`Need ${res.data.need_id} ingested`);

      // GAP-08: Poll status
      if (res.data.raw_id) {
        pollIngestStatus(res.data.raw_id);
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Ingestion failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="max-w-2xl space-y-6">
      <section className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm space-y-4">
        <h3 className="font-bold text-brand-900">Mobile Need Submission</h3>

        <div>
          <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Category</label>
          <select value={category} onChange={e => setCategory(e.target.value)}
            className="w-full bg-gray-50 rounded-xl p-3 text-sm border-none">
            {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        <div>
          <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Description</label>
          <textarea value={description} onChange={e => setDescription(e.target.value)}
            className="w-full bg-gray-50 rounded-xl p-3 text-sm border-none" rows={4}
            placeholder="Describe the need in detail..." />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Language</label>
            <select value={language} onChange={e => setLanguage(e.target.value)}
              className="w-full bg-gray-50 rounded-xl p-3 text-sm border-none">
              <option value="en">English</option>
              <option value="hi">Hindi</option>
              <option value="mr">Marathi</option>
              <option value="ta">Tamil</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Beneficiaries</label>
            <input type="number" value={beneficiaryCount} onChange={e => setBeneficiaryCount(+e.target.value)}
              className="w-full bg-gray-50 rounded-xl p-3 text-sm border-none" min={1} />
          </div>
        </div>

        <div>
          <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Location Text</label>
          <input type="text" value={locationText} onChange={e => setLocationText(e.target.value)}
            className="w-full bg-gray-50 rounded-xl p-3 text-sm border-none"
            placeholder="Near blue mosque, ward 12..." />
        </div>

        <div>
          <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Known Household ID (optional)</label>
          <input type="text" value={householdId} onChange={e => setHouseholdId(e.target.value)}
            className="w-full bg-gray-50 rounded-xl p-3 text-sm border-none" placeholder="HH-XXXXX" />
        </div>

        <button onClick={handleSubmit} disabled={isSubmitting}
          className="w-full bg-brand-600 text-white py-3 rounded-xl font-bold hover:bg-brand-800 transition-all disabled:opacity-50 flex items-center justify-center gap-2">
          {isSubmitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
          Submit Need
        </button>
      </section>

      {lastResult && (
        <section className="bg-green-50 p-4 rounded-2xl border border-green-200 text-sm space-y-1">
          <h4 className="font-bold text-green-800">Ingestion Result</h4>
          <p>Need ID: <span className="font-mono">{lastResult.need_id}</span></p>
          <p>Household: <span className="font-mono">{lastResult.household_id || 'N/A'}</span> ({lastResult.household_status})</p>
          <p>Duplicate: {lastResult.is_duplicate ? `Yes (of ${lastResult.duplicate_of})` : 'No'}</p>
          <p>Routed to Review: {lastResult.routed_to_review ? 'Yes' : 'No'}</p>
          <p>NLP Confidence: {lastResult.nlp_confidence?.toFixed(2)}</p>
        </section>
      )}
    </div>
  );
}

// ── TEXT INGEST (WhatsApp/SMS) ───────────────────────────────
function TextIngestForm() {
  const [text, setText] = useState('');
  const [source, setSource] = useState<'whatsapp' | 'sms'>('whatsapp');
  const [senderPhone, setSenderPhone] = useState('');
  const [languageHint, setLanguageHint] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!text) { toast.error('Text required'); return; }
    setIsSubmitting(true);
    try {
      const res = await NeedAPI.ingestText({
        text, source,
        sender_phone: senderPhone || undefined,
        language_hint: languageHint || undefined,
      });
      toast.success(`Text ingested → Need ${res.data.need_id}`);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Text ingestion failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="max-w-2xl space-y-6">
      <section className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm space-y-4">
        <h3 className="font-bold text-brand-900">WhatsApp / SMS Ingestion</h3>
        <div className="flex gap-2">
          {(['whatsapp', 'sms'] as const).map(s => (
            <button key={s} onClick={() => setSource(s)}
              className={`px-4 py-2 rounded-xl text-sm font-bold ${source === s ? 'bg-brand-600 text-white' : 'bg-gray-100 text-gray-600'}`}>
              {s.toUpperCase()}
            </button>
          ))}
        </div>
        <textarea value={text} onChange={e => setText(e.target.value)}
          className="w-full bg-gray-50 rounded-xl p-3 text-sm border-none" rows={5}
          placeholder="Paste message text..." />
        <div className="grid grid-cols-2 gap-4">
          <input type="text" value={senderPhone} onChange={e => setSenderPhone(e.target.value)}
            className="bg-gray-50 rounded-xl p-3 text-sm border-none" placeholder="Sender phone" />
          <input type="text" value={languageHint} onChange={e => setLanguageHint(e.target.value)}
            className="bg-gray-50 rounded-xl p-3 text-sm border-none" placeholder="Language hint (e.g. hi)" />
        </div>
        <button onClick={handleSubmit} disabled={isSubmitting}
          className="w-full bg-brand-600 text-white py-3 rounded-xl font-bold hover:bg-brand-800 disabled:opacity-50 flex items-center justify-center gap-2">
          {isSubmitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <MessageSquare className="w-4 h-4" />}
          Submit Text
        </button>
      </section>
    </div>
  );
}

// ── CSV INGEST ──────────────────────────────────────────────
function CsvIngestForm() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<any>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleUpload = async () => {
    if (!file) { toast.error('Select CSV file'); return; }
    setIsSubmitting(true);
    try {
      const res = await NeedAPI.ingestCsv(file);
      setResult(res.data);
      toast.success(`CSV processed: ${res.data.processed} of ${res.data.total}`);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'CSV upload failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="max-w-2xl space-y-6">
      <section className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm space-y-4">
        <h3 className="font-bold text-brand-900">CSV Bulk Upload</h3>
        <p className="text-xs text-gray-500">Required column: <code className="bg-gray-100 px-1 rounded">description</code></p>
        <input ref={fileRef} type="file" accept=".csv" onChange={e => setFile(e.target.files?.[0] || null)}
          className="w-full bg-gray-50 rounded-xl p-3 text-sm border-none" />
        <button onClick={handleUpload} disabled={isSubmitting || !file}
          className="w-full bg-brand-600 text-white py-3 rounded-xl font-bold hover:bg-brand-800 disabled:opacity-50 flex items-center justify-center gap-2">
          {isSubmitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
          Upload CSV
        </button>
      </section>
      {result && (
        <section className="bg-green-50 p-4 rounded-2xl border border-green-200 text-sm space-y-1">
          <p>Total: {result.total} | Processed: {result.processed} | Duplicates: {result.duplicates} | Errors: {result.errors}</p>
        </section>
      )}
    </div>
  );
}

// ── IMAGE INGEST ────────────────────────────────────────────
function ImageIngestForm() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [languageHints, setLanguageHints] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleUpload = async () => {
    if (!file) { toast.error('Select image'); return; }
    setIsSubmitting(true);
    try {
      const res = await NeedAPI.ingestImage(file, languageHints || undefined);
      toast.success(`Image ingested → Need ${res.data.need_id}`);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Image upload failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="max-w-2xl space-y-6">
      <section className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm space-y-4">
        <h3 className="font-bold text-brand-900">Image OCR Ingestion</h3>
        <input ref={fileRef} type="file" accept="image/*" onChange={e => setFile(e.target.files?.[0] || null)}
          className="w-full bg-gray-50 rounded-xl p-3 text-sm border-none" />
        <input type="text" value={languageHints} onChange={e => setLanguageHints(e.target.value)}
          className="w-full bg-gray-50 rounded-xl p-3 text-sm border-none" placeholder="Language hints (comma-sep)" />
        <button onClick={handleUpload} disabled={isSubmitting || !file}
          className="w-full bg-brand-600 text-white py-3 rounded-xl font-bold hover:bg-brand-800 disabled:opacity-50 flex items-center justify-center gap-2">
          {isSubmitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Image className="w-4 h-4" />}
          Upload Image
        </button>
      </section>
    </div>
  );
}

// ── REVIEW QUEUE ────────────────────────────────────────────
function ReviewQueue() {
  const [reviews, setReviews] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchReviews = async () => {
    setIsLoading(true);
    try {
      const res = await NeedAPI.getReviewQueue(50);
      setReviews(Array.isArray(res.data) ? res.data : res.data.items || []);
    } catch {
      toast.error('Failed to load review queue');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { fetchReviews(); }, []);

  const handleApprove = async (id: string) => {
    try {
      await NeedAPI.approveReview(id, {});
      toast.success(`Review ${id} approved`);
      fetchReviews();
    } catch { toast.error('Approve failed'); }
  };

  const handleReject = async (id: string) => {
    try {
      await NeedAPI.rejectReview(id, {});
      toast.success(`Review ${id} rejected`);
      fetchReviews();
    } catch { toast.error('Reject failed'); }
  };

  if (isLoading) return <div className="flex items-center gap-2 py-10 justify-center text-gray-500"><Loader2 className="w-5 h-5 animate-spin" /> Loading reviews...</div>;

  if (reviews.length === 0) return (
    <div className="text-center py-16 text-gray-400">
      <CheckCircle className="w-12 h-12 mx-auto mb-3 opacity-30" />
      <p className="font-medium">Review queue empty</p>
    </div>
  );

  return (
    <div className="space-y-3 max-w-3xl">
      {reviews.map((r: any) => (
        <div key={r.review_id || r.id} className="bg-white p-4 rounded-2xl border border-gray-100 shadow-sm flex items-start justify-between">
          <div className="flex-1">
            <p className="font-bold text-sm text-brand-900">{r.review_type || 'review'}</p>
            <p className="text-xs text-gray-500 mt-1 line-clamp-2">{r.description || r.text || JSON.stringify(r.data || {}).slice(0, 120)}</p>
          </div>
          <div className="flex gap-2 ml-4 shrink-0">
            <button onClick={() => handleApprove(r.review_id || r.id)}
              className="p-2 bg-green-50 text-green-600 rounded-xl hover:bg-green-100">
              <CheckCircle className="w-4 h-4" />
            </button>
            <button onClick={() => handleReject(r.review_id || r.id)}
              className="p-2 bg-red-50 text-red-500 rounded-xl hover:bg-red-100">
              <XCircle className="w-4 h-4" />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── GAP-08: Poll ingest status (graceful if 404) ────────────
function pollIngestStatus(raw_id: string) {
  let attempts = 0;
  const maxAttempts = 15;
  const interval = setInterval(async () => {
    attempts++;
    try {
      const res = await NeedAPI.getIngestStatus(raw_id);
      if (res.data?.status === 'processed' || res.data?.status === 'completed') {
        clearInterval(interval);
        toast.success(`Ingestion ${raw_id} processed`);
      }
    } catch (err: any) {
      if (err?.response?.status === 404) {
        // GAP-08: endpoint not built yet — graceful
        clearInterval(interval);
        // Silent — no crash
      }
    }
    if (attempts >= maxAttempts) clearInterval(interval);
  }, 2000);
}
