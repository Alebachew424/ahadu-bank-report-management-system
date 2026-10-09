import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert, Box, Button, Chip, Collapse, CircularProgress,
  Divider, LinearProgress, MenuItem, Paper,
  Stack, TextField, Tooltip, Typography,
} from '@mui/material';
import {
  AttachFileOutlined, AutoAwesomeOutlined,
  ChatBubbleOutlineOutlined,
  ExpandLess, ExpandMore,
  PsychologyOutlined, WarningAmberOutlined,
} from '@mui/icons-material';
import { requestsAPI } from '../../api/requests';
import { aiAPI, type AiAnalysis } from '../../api/ai';

interface RequestType {
  id: number;
  name: string;
  description: string | null;
  form_schema: Record<string, unknown>;
}

type PreviousResponse = {
  ticket_id: number;
  title: string;
  description: string | null;
  status: string;
  closed_at: string;
  attachments: { id: number; file_name: string; is_final: boolean; version: number }[];
  comments: { id: number; body: string; created_at: string }[];
} | null;

const PRIORITY_COLOUR: Record<string, 'default' | 'info' | 'warning' | 'error'> = {
  low: 'default', medium: 'info', high: 'warning', urgent: 'error',
};

const SEVERITY_COLOUR: Record<string, 'info' | 'warning' | 'error'> = {
  low: 'info', medium: 'warning', high: 'error',
};

// ── debounce helper ──────────────────────────────────────────────────────────
function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

// ── confidence bar ───────────────────────────────────────────────────────────
function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 70 ? '#2e6b57' : pct >= 40 ? '#a06b32' : '#888';
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <LinearProgress
        variant="determinate"
        value={pct}
        sx={{
          flex: 1, height: 6, borderRadius: 3, bgcolor: '#e8e0e4',
          '& .MuiLinearProgress-bar': { bgcolor: color },
        }}
      />
      <Typography variant="caption" fontWeight={700} sx={{ color, minWidth: 34 }}>
        {pct}%
      </Typography>
    </Box>
  );
}

// ── main component ───────────────────────────────────────────────────────────
export function RequestCreate() {
  const navigate = useNavigate();

  const [form, setForm] = useState({
    title: '', description: '', priority: 'medium', due_date: '', request_type_id: 0,
  });
  const [types,        setTypes]        = useState<RequestType[]>([]);
  const [error,        setError]        = useState('');
  const [saving,       setSaving]       = useState(false);
  const [loadingTypes, setLoadingTypes] = useState(true);

  // previous-response state
  const [prevResponse,  setPrevResponse]  = useState<PreviousResponse>(null);
  const [prevExpanded,  setPrevExpanded]  = useState(true);
  const [autoFilled,    setAutoFilled]    = useState(false);

  // ── AI state ──────────────────────────────────────────────────────────────
  const [aiResult,    setAiResult]    = useState<AiAnalysis | null>(null);
  const [aiLoading,   setAiLoading]   = useState(false);
  const [aiExpanded,  setAiExpanded]  = useState(true);
  const debounceTitle = useDebounce(form.title, 800);
  const debounceDesc  = useDebounce(form.description, 800);
  const lastAiReq     = useRef('');

  // Load request types on mount
  useEffect(() => {
    requestsAPI.listTypes()
      .then((res) => {
        setTypes(res.data);
        if (res.data[0]) setForm((f) => ({ ...f, request_type_id: res.data[0].id }));
      })
      .catch(() => setError('Unable to load report types'))
      .finally(() => setLoadingTypes(false));
  }, []);

  // When the report type changes, check for a previous response
  useEffect(() => {
    if (!form.request_type_id) return;
    setPrevResponse(null);
    setAutoFilled(false);

    requestsAPI.previousResponse(form.request_type_id)
      .then((res) => {
        if (res.data) {
          setPrevResponse(res.data);
          setPrevExpanded(true);
        }
      })
      .catch(() => undefined);
  }, [form.request_type_id]);

  // ── AI analysis — fires 800 ms after user stops typing title ──────────────
  useEffect(() => {
    const title = debounceTitle.trim();
    if (title.length < 5) {
      setAiResult(null);
      return;
    }
    const key = `${title}|${debounceDesc}|${form.priority}|${form.request_type_id}`;
    if (key === lastAiReq.current) return;
    lastAiReq.current = key;

    setAiLoading(true);
    aiAPI.analyse({
      title,
      description:     debounceDesc || null,
      priority:        form.priority,
      request_type_id: form.request_type_id || null,
    })
      .then((res) => { setAiResult(res.data); setAiExpanded(true); })
      .catch(() => undefined)   // silent — AI is advisory only
      .finally(() => setAiLoading(false));
  }, [debounceTitle, debounceDesc, form.priority, form.request_type_id]);

  const update = (field: string, value: string | number) =>
    setForm((f) => ({ ...f, [field]: value }));

  const applyPrevious = () => {
    if (!prevResponse) return;
    setForm((f) => ({
      ...f,
      title:       prevResponse.title,
      description: prevResponse.description ?? '',
    }));
    setAutoFilled(true);
  };

  // Apply AI-suggested request type
  const applyAiType = (typeId: number) => {
    setForm((f) => ({ ...f, request_type_id: typeId }));
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      const res = await requestsAPI.create({
        ...form,
        request_type_id: form.request_type_id,
        due_date: new Date(`${form.due_date}T23:59:00`).toISOString(),
        priority: form.priority as 'low' | 'medium' | 'high' | 'urgent',
      });
      navigate(`/requests/${res.data.id}`);
    } catch (err: unknown) {
      const detail =
        typeof err === 'object' && err !== null && 'response' in err
          ? (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
          : undefined;
      setError(
        Array.isArray(detail)
          ? detail.map((i) => (typeof i === 'object' && i !== null && 'msg' in i ? String((i as { msg: unknown }).msg) : String(i))).join(', ')
          : typeof detail === 'string' ? detail : 'Unable to create request',
      );
    } finally {
      setSaving(false);
    }
  };

  const hasAnomalies   = (aiResult?.anomalies?.anomalies?.length ?? 0) > 0;
  const flagged        = aiResult?.anomalies?.flagged ?? false;
  const suggestions    = aiResult?.categorisation?.suggestions ?? [];
  const analysts       = aiResult?.analyst_suggestion?.suggestions ?? [];
  const anomalies      = aiResult?.anomalies?.anomalies ?? [];

  return (
    <Stack spacing={3} sx={{ maxWidth: 780 }}>
      <Box>
        <Typography variant="h5" fontWeight={700}>New Report Request</Typography>
        <Typography variant="body2" color="text.secondary">
          Fill in the details below. Your request will go to your department manager for approval first.
        </Typography>
      </Box>

      {error && <Alert severity="error">{error}</Alert>}

      {/* ── Previous response suggestion panel ── */}
      {prevResponse && (
        <Paper variant="outlined" sx={{ borderColor: '#7B1235', borderRadius: 2, overflow: 'hidden' }}>
          <Box
            sx={{ px: 2.5, py: 1.5, bgcolor: '#fdf6f8', display: 'flex', alignItems: 'center', gap: 1, cursor: 'pointer', userSelect: 'none' }}
            onClick={() => setPrevExpanded((v) => !v)}
          >
            <AutoAwesomeOutlined sx={{ color: '#7B1235', fontSize: 20 }} />
            <Typography variant="body2" fontWeight={700} sx={{ color: '#7B1235', flexGrow: 1 }}>
              Previous response found — Ticket #{String(prevResponse.ticket_id).padStart(5, '0')}
            </Typography>
            <Chip size="small" label={prevResponse.status} color="success" sx={{ fontSize: 11, fontWeight: 600 }} />
            {prevExpanded ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
          </Box>

          <Collapse in={prevExpanded}>
            <Box sx={{ px: 2.5, pb: 2.5, pt: 1 }}>
              <Typography variant="caption" color="text.secondary">
                Last submitted {new Date(prevResponse.closed_at).toLocaleDateString()} · Same report type
              </Typography>
              <Divider sx={{ my: 1.5 }} />
              <Typography variant="body2" fontWeight={600} gutterBottom>{prevResponse.title}</Typography>
              {prevResponse.description && (
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>{prevResponse.description}</Typography>
              )}
              {prevResponse.attachments.length > 0 && (
                <Box sx={{ mb: 1.5 }}>
                  <Typography variant="caption" fontWeight={700} sx={{ display: 'flex', alignItems: 'center', gap: .5, mb: .5 }}>
                    <AttachFileOutlined sx={{ fontSize: 14 }} /> Previous deliverables
                  </Typography>
                  <Stack spacing={.5}>
                    {prevResponse.attachments.map((a) => (
                      <Box key={a.id} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="body2">{a.file_name}</Typography>
                        {a.is_final && <Chip label="Final" size="small" color="success" sx={{ fontSize: 10 }} />}
                      </Box>
                    ))}
                  </Stack>
                </Box>
              )}
              {prevResponse.comments.length > 0 && (
                <Box sx={{ mb: 2 }}>
                  <Typography variant="caption" fontWeight={700} sx={{ display: 'flex', alignItems: 'center', gap: .5, mb: .5 }}>
                    <ChatBubbleOutlineOutlined sx={{ fontSize: 14 }} /> Previous MIS response
                  </Typography>
                  <Stack spacing={.5}>
                    {prevResponse.comments.map((c) => (
                      <Box key={c.id} sx={{ pl: 1.5, borderLeft: '3px solid #7B123540' }}>
                        <Typography variant="body2">{c.body}</Typography>
                        <Typography variant="caption" color="text.secondary">{new Date(c.created_at).toLocaleString()}</Typography>
                      </Box>
                    ))}
                  </Stack>
                </Box>
              )}
              <Box sx={{ display: 'flex', gap: 1.5, mt: 1 }}>
                <Button size="small" variant="contained"
                  sx={{ bgcolor: '#7B1235', '&:hover': { bgcolor: '#5f0d29' } }}
                  onClick={applyPrevious} disabled={autoFilled}>
                  {autoFilled ? '✓ Applied to form' : 'Use previous title & description'}
                </Button>
                <Button size="small" variant="outlined" onClick={() => navigate(`/requests/${prevResponse.ticket_id}`)}>
                  View previous ticket
                </Button>
              </Box>
            </Box>
          </Collapse>
        </Paper>
      )}

      {/* ── AI INTELLIGENCE PANEL ── */}
      {(aiLoading || aiResult) && (
        <Paper
          variant="outlined"
          sx={{
            borderColor: flagged ? '#d32f2f' : '#7B1235',
            borderRadius: 2,
            overflow: 'hidden',
          }}
        >
          {/* header */}
          <Box
            sx={{
              px: 2.5, py: 1.5,
              bgcolor: flagged ? '#fff5f5' : '#fdf6f8',
              display: 'flex', alignItems: 'center', gap: 1,
              cursor: 'pointer', userSelect: 'none',
            }}
            onClick={() => setAiExpanded((v) => !v)}
          >
            <PsychologyOutlined sx={{ color: flagged ? '#d32f2f' : '#7B1235', fontSize: 20 }} />
            <Typography variant="body2" fontWeight={700} sx={{ color: flagged ? '#d32f2f' : '#7B1235', flexGrow: 1 }}>
              AI Analysis
              {aiLoading && <CircularProgress size={12} sx={{ ml: 1, color: 'inherit' }} />}
              {flagged && !aiLoading && (
                <Chip size="small" label="Anomaly detected" color="error" sx={{ ml: 1, fontSize: 10, fontWeight: 700 }} />
              )}
            </Typography>
            {aiExpanded ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
          </Box>

          <Collapse in={aiExpanded && !aiLoading}>
            <Stack spacing={0} divider={<Divider />}>

              {/* ── Anomaly warnings ── */}
              {anomalies.length > 0 && (
                <Box sx={{ px: 2.5, py: 2 }}>
                  <Typography variant="caption" fontWeight={700} sx={{ color: '#888', letterSpacing: .6, textTransform: 'uppercase', display: 'block', mb: 1 }}>
                    ⚠ Anomaly Flags
                  </Typography>
                  <Stack spacing={1}>
                    {anomalies.map((a, i) => (
                      <Alert
                        key={i}
                        severity={SEVERITY_COLOUR[a.severity] ?? 'info'}
                        icon={<WarningAmberOutlined fontSize="small" />}
                        sx={{ py: 0.5, '& .MuiAlert-message': { fontSize: 13 } }}
                      >
                        {a.message}
                      </Alert>
                    ))}
                  </Stack>
                </Box>
              )}

              {/* ── Category suggestions ── */}
              {suggestions.length > 0 && (
                <Box sx={{ px: 2.5, py: 2 }}>
                  <Typography variant="caption" fontWeight={700} sx={{ color: '#888', letterSpacing: .6, textTransform: 'uppercase', display: 'block', mb: 1.5 }}>
                    🧠 Suggested Report Type
                  </Typography>
                  <Stack spacing={1.5}>
                    {suggestions.map((s) => {
                      const isCurrent = s.request_type_id === form.request_type_id;
                      return (
                        <Box
                          key={s.request_type_id}
                          sx={{
                            p: 1.5,
                            borderRadius: 1.5,
                            border: '1px solid',
                            borderColor: isCurrent ? '#7B1235' : '#e8e0e4',
                            bgcolor: isCurrent ? '#fdf6f8' : 'transparent',
                          }}
                        >
                          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
                            <Typography variant="body2" fontWeight={isCurrent ? 700 : 500}>
                              {s.name}
                              {isCurrent && (
                                <Chip label="Selected" size="small" color="success" sx={{ ml: 1, fontSize: 10 }} />
                              )}
                            </Typography>
                            {!isCurrent && (
                              <Button size="small" variant="outlined"
                                sx={{ fontSize: 11, py: 0, px: 1, minWidth: 0 }}
                                onClick={() => applyAiType(s.request_type_id)}>
                                Apply
                              </Button>
                            )}
                          </Box>
                          <ConfidenceBar value={s.confidence} />
                          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                            {s.reason}
                          </Typography>
                        </Box>
                      );
                    })}
                  </Stack>
                </Box>
              )}

              {/* ── Analyst suggestions ── */}
              {analysts.length > 0 && (
                <Box sx={{ px: 2.5, py: 2 }}>
                  <Typography variant="caption" fontWeight={700} sx={{ color: '#888', letterSpacing: .6, textTransform: 'uppercase', display: 'block', mb: 1.5 }}>
                    👤 Recommended MIS Officers
                  </Typography>
                  <Stack spacing={1}>
                    {analysts.slice(0, 3).map((a, i) => (
                      <Box
                        key={a.officer_id}
                        sx={{
                          display: 'flex', alignItems: 'center', gap: 1.5,
                          p: 1.2, borderRadius: 1.5, bgcolor: i === 0 ? '#f0f7f4' : 'transparent',
                          border: i === 0 ? '1px solid #2e6b5730' : 'none',
                        }}
                      >
                        <Box
                          sx={{
                            width: 28, height: 28, borderRadius: '50%',
                            bgcolor: i === 0 ? '#2e6b57' : '#ccc',
                            color: '#fff', display: 'flex', alignItems: 'center',
                            justifyContent: 'center', fontSize: 12, fontWeight: 700, flexShrink: 0,
                          }}
                        >
                          {i + 1}
                        </Box>
                        <Box sx={{ flex: 1, minWidth: 0 }}>
                          <Typography variant="body2" fontWeight={600} noWrap>
                            {a.name}
                          </Typography>
                          <Typography variant="caption" color="text.secondary" noWrap>
                            {a.reason}
                          </Typography>
                        </Box>
                        <Tooltip title={`Score: ${(a.score * 100).toFixed(0)}%`}>
                          <Box sx={{ textAlign: 'right', flexShrink: 0 }}>
                            <Typography variant="caption" fontWeight={700} sx={{ color: i === 0 ? '#2e6b57' : '#888' }}>
                              {(a.score * 100).toFixed(0)}%
                            </Typography>
                          </Box>
                        </Tooltip>
                      </Box>
                    ))}
                    <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
                      These suggestions will be visible to the MIS Manager when assigning.
                    </Typography>
                  </Stack>
                </Box>
              )}

            </Stack>
          </Collapse>
        </Paper>
      )}

      {/* ── Request form ── */}
      <Paper component="form" onSubmit={submit} sx={{ p: 3 }}>
        <Stack spacing={2.5}>
          <TextField
            select
            label="Report type"
            value={form.request_type_id}
            onChange={(e) => update('request_type_id', Number(e.target.value))}
            required
            disabled={loadingTypes}
            helperText={loadingTypes ? 'Loading types…' : 'Select the category of report you need'}
          >
            {types.map((t) => (
              <MenuItem key={t.id} value={t.id}>
                <Box>
                  <Typography variant="body2" fontWeight={600}>{t.name}</Typography>
                  {t.description && (
                    <Typography variant="caption" color="text.secondary">{t.description}</Typography>
                  )}
                </Box>
              </MenuItem>
            ))}
          </TextField>

          <TextField
            label="Title"
            value={form.title}
            onChange={(e) => update('title', e.target.value)}
            required
            placeholder="e.g. Daily Transaction Summary – Branch X"
            helperText="AI analysis starts after you type at least 5 characters"
          />

          <TextField
            label="Description / instructions"
            value={form.description}
            onChange={(e) => update('description', e.target.value)}
            multiline
            minRows={4}
            placeholder="Describe what you need, the date range, branch, format, or any other details…"
          />

          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            <TextField
              select
              label="Priority"
              value={form.priority}
              onChange={(e) => update('priority', e.target.value)}
              sx={{ minWidth: 150 }}
            >
              {[
                { value: 'low',    label: 'Low' },
                { value: 'medium', label: 'Medium' },
                { value: 'high',   label: 'High' },
                { value: 'urgent', label: 'Urgent' },
              ].map((p) => (
                <MenuItem key={p.value} value={p.value}>
                  <Chip
                    size="small"
                    label={p.label}
                    color={PRIORITY_COLOUR[p.value]}
                    variant="outlined"
                    sx={{ mr: 1, fontSize: 11 }}
                  />
                </MenuItem>
              ))}
            </TextField>

            <TextField
              label="Due date"
              type="date"
              value={form.due_date}
              onChange={(e) => update('due_date', e.target.value)}
              required
              sx={{ minWidth: 180 }}
              slotProps={{ inputLabel: { shrink: true } }}
              helperText="When do you need this report by?"
            />
          </Box>

          <Divider />

          <Box sx={{ display: 'flex', gap: 2 }}>
            <Button
              type="submit"
              variant="contained"
              size="large"
              disabled={saving || loadingTypes || !form.request_type_id}
              sx={{ bgcolor: '#7B1235', '&:hover': { bgcolor: '#5f0d29' } }}
            >
              {saving ? 'Submitting…' : 'Submit request'}
            </Button>
            <Button size="large" onClick={() => navigate('/')}>
              Cancel
            </Button>
          </Box>
        </Stack>
      </Paper>
    </Stack>
  );
}
