import axios from 'axios'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export const api = axios.create({
  baseURL: `${API_URL}/api`,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Deal types
export interface Deal {
  id: number
  state: string
  acquirer_cik?: string
  acquirer_name_display?: string
  target_cik?: string
  target_name_display?: string
  announcement_date?: string
  agreement_date?: string
  deal_value_usd?: number
  is_sponsor_backed?: boolean
  sponsor_name_display?: string
  market_tag?: string
  advisory_fee_estimated?: number
  underwriting_fee_estimated?: number
  created_at: string
}

export interface FinancingEvent {
  id: number
  deal_id: number
  instrument_family: string
  instrument_type?: string
  market_tag?: string
  amount_usd?: number
  amount_raw?: string
  purpose?: string
  reconciliation_confidence?: number
  reconciliation_explanation?: string
  estimated_fee_usd?: number
  participants: FinancingParticipant[]
}

export interface FinancingParticipant {
  id: number
  bank_name_raw: string
  bank_name_normalized?: string
  role: string
  role_normalized?: string
  evidence_snippet?: string
  estimated_fee_usd?: number
}

export interface Filing {
  id: number
  accession_number: string
  cik: string
  form_type: string
  filing_date: string
  company_name?: string
  filing_url?: string
  processed: boolean
}

export interface Alert {
  id: number
  alert_type: string
  title: string
  description?: string
  filing_id?: number
  exhibit_id?: number
  deal_id?: number
  exhibit_link?: string
  fields_needed?: string[]
  is_resolved: boolean
  resolved_at?: string
  resolved_by?: string
  created_at: string
}

// API functions
export async function getDeals(params?: {
  query?: string
  is_sponsor_backed?: boolean
  market_tag?: string
  limit?: number
  offset?: number
}): Promise<Deal[]> {
  const { data } = await api.get('/deals', { params })
  return data
}

export async function getDeal(id: number): Promise<Deal> {
  const { data } = await api.get(`/deals/${id}`)
  return data
}

export async function getDealFinancing(id: number): Promise<FinancingEvent[]> {
  const { data } = await api.get(`/deals/${id}/financing`)
  return data
}

export async function getDealAdvisors(id: number): Promise<any[]> {
  const { data } = await api.get(`/deals/${id}/advisors`)
  return data
}

export async function getDealFacts(id: number): Promise<any[]> {
  const { data } = await api.get(`/deals/${id}/facts`)
  return data
}

export async function getFilings(params?: {
  cik?: string
  form_type?: string
  processed?: boolean
  limit?: number
  offset?: number
}): Promise<Filing[]> {
  const { data } = await api.get('/filings', { params })
  return data
}

export async function getFiling(id: number): Promise<Filing> {
  const { data } = await api.get(`/filings/${id}`)
  return data
}

export async function ingestFilings(params: {
  cik: string
  form_types?: string[]
  start_date?: string
  end_date?: string
}): Promise<any> {
  const { data } = await api.post('/filings/ingest', params)
  return data
}

export async function getAlerts(params?: {
  alert_type?: string
  is_resolved?: boolean
  limit?: number
}): Promise<Alert[]> {
  const { data } = await api.get('/alerts', { params })
  return data
}

export async function getUnresolvedAlerts(): Promise<Alert[]> {
  const { data } = await api.get('/alerts/unresolved')
  return data
}

export async function resolveAlert(id: number, params: {
  resolved_by: string
  resolution_notes?: string
}): Promise<any> {
  const { data } = await api.post(`/alerts/${id}/resolve`, params)
  return data
}

export async function search(q: string): Promise<any> {
  const { data } = await api.get('/search', { params: { q } })
  return data
}

export async function runPipeline(): Promise<any> {
  const { data } = await api.post('/pipeline/run')
  return data
}

export async function getDealStats(): Promise<any> {
  const { data } = await api.get('/deals/stats/summary')
  return data
}

export async function getFilingStats(): Promise<any> {
  const { data } = await api.get('/filings/stats/summary')
  return data
}

export async function getAlertStats(): Promise<any> {
  const { data } = await api.get('/alerts/stats/summary')
  return data
}
