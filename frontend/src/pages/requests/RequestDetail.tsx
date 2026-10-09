/**
 * RequestDetail — full ticket view with role-aware workflow actions.
 *
 * Workflow:
 *   Requester         → create, cancel (early), submit feedback (Resolved)
 *   Requester Manager → approve / reject   (Pending Dept Approval)
 *   MIS Manager       → assign to officer  (Submitted)
 *   MIS Officer       → start / resolve / request-clarification / resume
 */

import { useEffect, useState } from 'react';
import {
  Alert, Box, Button, Chip, Dialog, DialogContent, DialogTitle,
  Divider, FormControlLabel, Checkbox, IconButton,
  List, ListItem, ListItemText,
  MenuItem, Paper, Rating,
  Stack, TextField, Tooltip, Typography,
} from '@mui/material';
import { CloseOutlined, VisibilityOutlined, WarningAmberOutlined } from '@mui/icons-material';
import { useNavigate, useParams } from 'react-router-dom';
import { attachmentsAPI } from '../../api/attachments';
import { commentsAPI } from '../../api/comments';
import { requestsAPI, type RequestFeedback } from '../../api/requests';
import { authAPI } from '../../api/auth';
import { usersAPI } from '../../api/users';
import type { ReportRequest } from '../../types/types';
import type { TicketComment } from '../../api/comments';

interface Attachment { id: number; file_name: string; version: number; is_final: boolean; created_at: string; }
interface MISUser    { id: number; full_name: string | null; email: string; role_name: string | null; }

// ── file preview helpers ──────────────────────────────────────────────────────
type PreviewState = {
  name: string;
  type: 'image' | 'pdf' | 'excel' | 'word' | 'text' | 'unsupported';
  // for image/pdf/text: object URL or text content
  url?: string;
  // for excel: array of { name, html }
  sheets?: { name: string; html: string }[];
  // for word: html string
  html?: string;
} | null;

function getFileType(fileName: string): PreviewState['type'] {
  const ext = fileName.split('.').pop()?.toLowerCase() ?? '';
  if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp'].includes(ext)) return 'image';
  if (ext === 'pdf') return 'pdf';
  if (['xlsx', 'xls', 'csv'].includes(ext)) return 'excel';
  if (['docx', 'doc'].includes(ext)) return 'word';
  if (['txt', 'json', 'xml', 'html', 'md', 'log', 'jsx', 'tsx', 'ts', 'js', 'py'].includes(ext)) return 'text';
  return 'unsupported';
}

const STATUS_COLOUR: Record<string, 'default' | 'warning' | 'info' | 'primary' | 'success' | 'error'> = {
  'Pending Dept Approval': 'warning',
  'Submitted':             'info',
  'Assigned':              'info',
  'In Progress':           'primary',
  'Needs Clarification':   'warning',
  'Resolved':              'success',
  'Closed':                'success',
  'Rejected':              'error',
  'Cancelled':             'error',
};

const MIS_MANAGER_ROLES = ['MIS Manager', 'MIS Supervisor', 'Admin', 'System Administrator'];
const MIS_ROLES         = ['MIS Officer', 'MIS Analyst', ...MIS_MANAGER_ROLES];

export function RequestDetail() {
  const { id }     = useParams();
  const navigate   = useNavigate();

  // ── data ──────────────────────────────────────────────────────────────────
  const [request,     setRequest]     = useState<ReportRequest | null>(null);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [comments,    setComments]    = useState<TicketComment[]>([]);
  const [feedback,    setFeedback]    = useState<RequestFeedback | null>(null);
  const [misUsers,    setMisUsers]    = useState<MISUser[]>([]);
  const [assignTo,    setAssignTo]    = useState<number>(0);

  // ── current user ──────────────────────────────────────────────────────────
  const [myId,          setMyId]          = useState(0);
  const [myRoleName,    setMyRoleName]    = useState('');
  const [isDeptManager, setIsDeptManager] = useState(false);
  const [isMIS,         setIsMIS]         = useState(false);
  const [isMISManager,  setIsMISManager]  = useState(false);

  // ── form state ────────────────────────────────────────────────────────────
  const [commentText, setCommentText] = useState('');
  const [internal,    setInternal]    = useState(false);
  const [uploading,   setUploading]   = useState(false);
  const [quality,     setQuality]     = useState(0);
  const [timeliness,  setTimeliness]  = useState(0);
  const [feedbackNote,setFeedbackNote]= useState('');
  const [error,       setError]       = useState('');

  // preview modal
  const [preview, setPreview] = useState<PreviewState>(null);

  // ── load everything at once ───────────────────────────────────────────────
  useEffect(() => {
    if (!id) return;
    const numId = Number(id);

    const load = async () => {
      try {
        const [rRes, aRes, cRes, uRes] = await Promise.all([
          requestsAPI.get(numId),
          attachmentsAPI.list(numId),
          commentsAPI.list(numId),
          authAPI.me(),
        ]);

        setRequest(rRes.data);
        setAttachments(aRes.data);
        setComments(cRes.data);

        const u = uRes.data;
        console.log('[RequestDetail] me:', u.role_name, u.role_type);

        setMyId(u.id ?? 0);
        setMyRoleName(u.role_name);
        setIsDeptManager(u.role_type === 'Manager' && u.role_name === 'Requester Manager');
        setIsMIS(MIS_ROLES.includes(u.role_name));

        const isMgr = MIS_MANAGER_ROLES.includes(u.role_name);
        setIsMISManager(isMgr);
        console.log('[RequestDetail] isMISManager:', isMgr, '| status:', rRes.data.status_name);

        if (isMgr) {
          try {
            const teamRes = await usersAPI.misTeam();
            console.log('[RequestDetail] mis-team:', teamRes.data);
            setMisUsers(teamRes.data as MISUser[]);
            if (teamRes.data.length > 0) setAssignTo(teamRes.data[0].id);
          } catch (e) {
            console.error('[RequestDetail] mis-team failed:', e);
          }
        }

        requestsAPI.getFeedback(numId).then((fRes) => setFeedback(fRes.data)).catch(() => undefined);
      } catch {
        setError('Unable to load this ticket');
      }
    };

    load();
  }, [id]);

  // ── guards ────────────────────────────────────────────────────────────────
  if (error && !request) return <Alert severity="error">{error}</Alert>;
  if (!request)          return <Typography>Loading ticket…</Typography>;

  const status = request.status_name ?? '';

  // ── action helpers ────────────────────────────────────────────────────────
  const act = async (fn: () => Promise<{ data: ReportRequest }>) => {
    setError('');
    try { setRequest((await fn()).data); }
    catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail;
      setError(detail ?? 'Action failed');
    }
  };

  const upload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !id) return;
    setUploading(true);
    try   { const res = await attachmentsAPI.upload(Number(id), file); setAttachments((p) => [...p, res.data]); }
    catch { setError('Unable to upload file'); }
    finally { setUploading(false); e.target.value = ''; }
  };

  const download = async (att: Attachment) => {
    const res = await attachmentsAPI.download(att.id);
    const url = URL.createObjectURL(res.data);
    Object.assign(document.createElement('a'), { href: url, download: att.file_name }).click();
    URL.revokeObjectURL(url);
  };

  const openPreview = async (att: Attachment) => {
    const type = getFileType(att.file_name);
    if (type === 'unsupported') {
      setPreview({ name: att.file_name, type: 'unsupported' });
      return;
    }
    const res = await attachmentsAPI.download(att.id);
    const blob: Blob = res.data;

    if (type === 'image') {
      setPreview({ name: att.file_name, type: 'image', url: URL.createObjectURL(blob) });

    } else if (type === 'pdf') {
      setPreview({ name: att.file_name, type: 'pdf', url: URL.createObjectURL(blob) });

    } else if (type === 'text') {
      const text = await blob.text();
      setPreview({ name: att.file_name, type: 'text', html: text });

    } else if (type === 'excel') {
      const XLSX = await import('xlsx');
      const workbook = XLSX.read(await blob.arrayBuffer(), { type: 'array' });
      const sheets = workbook.SheetNames.map((name) => ({
        name,
        html: XLSX.utils.sheet_to_html(workbook.Sheets[name]),
      }));
      setPreview({ name: att.file_name, type: 'excel', sheets });

    } else if (type === 'word') {
      const mammoth = await import('mammoth');
      const result = await mammoth.convertToHtml({ arrayBuffer: await blob.arrayBuffer() });
      setPreview({ name: att.file_name, type: 'word', html: result.value });
    }
  };

  const closePreview = () => {
    if (preview?.url) URL.revokeObjectURL(preview.url);
    setPreview(null);
  };

  const addComment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id || !commentText.trim()) return;
    try {
      const res = await commentsAPI.create(Number(id), commentText, internal);
      setComments((p) => [...p, res.data]);
      setCommentText('');
    } catch { setError('Unable to send message'); }
  };

  const doAssign = () => {
    if (!id || !assignTo) return;
    act(() => requestsAPI.assign(Number(id), assignTo));
  };

  const submitFeedback = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id || !quality || !timeliness) return;
    try {
      const fRes = await requestsAPI.createFeedback(Number(id), {
        quality_rating: quality, timeliness_rating: timeliness, comment: feedbackNote || null,
      });
      setFeedback(fRes.data);
      const rRes = await requestsAPI.get(Number(id));
      setRequest(rRes.data);
    } catch { setError('Unable to submit feedback'); }
  };

  // ── what can this user do RIGHT NOW? ──────────────────────────────────────
  const isRequester       = request.requester_id === myId;
  const isAssignedOfficer = request.assigned_to_id === myId;

  const canDeptApprove = isDeptManager  && status === 'Pending Dept Approval';
  const canDeptReject  = isDeptManager  && status === 'Pending Dept Approval';
  const canAssign      = isMISManager   && status === 'Submitted';

  console.log('[RequestDetail] render | isMISManager:', isMISManager, '| status:', status, '| canAssign:', canAssign, '| misUsers:', misUsers.length);
  const canStart       = isMIS && (isAssignedOfficer || isMISManager) && status === 'Assigned';
  const canResolve     = isMIS && (isAssignedOfficer || isMISManager) && status === 'In Progress';
  const canClarify     = isMIS && (isAssignedOfficer || isMISManager) && status === 'In Progress';
  const canResume      = isMIS && (isAssignedOfficer || isMISManager) && status === 'Needs Clarification';
  const canCancel      = isRequester    && ['Pending Dept Approval', 'Submitted'].includes(status);
  const canFeedback    = isRequester    && status === 'Resolved' && !feedback;

  // ── render ────────────────────────────────────────────────────────────────
  return (
    <Stack spacing={2}>
      <Button onClick={() => navigate('/')} sx={{ alignSelf: 'flex-start' }}>← Back</Button>

      {/* header */}
      <Paper sx={{ p: 3 }}>
        <Stack spacing={1}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
            <Typography variant="h5" sx={{ flexGrow: 1 }}>{request.title}</Typography>
            <Chip label={status || `Status ${request.status_id}`} color={STATUS_COLOUR[status] ?? 'default'} />
            <Chip label={request.priority} variant="outlined" size="small" />
          </Box>
          <Typography color="text.secondary" variant="body2">
            Ticket #{String(request.id).padStart(5, '0')} · Due {new Date(request.due_date).toLocaleDateString()}
          </Typography>
          <Divider />
          <Typography>{request.description || 'No description provided.'}</Typography>
        </Stack>
      </Paper>

      {error && <Alert severity="error" onClose={() => setError('')}>{error}</Alert>}

      {/* ── SLA STATUS PANEL ── */}
      {request.sla_deadline && (() => {
        const terminal = ['Closed','Resolved','Rejected','Cancelled'].includes(status);
        if (terminal) return null;
        const hrs = request.sla_hours_remaining;
        const overdue = request.sla_overdue;
        const deadline = new Date(request.sla_deadline).toLocaleString();
        if (overdue) {
          const hoursOver = hrs !== null ? Math.abs(hrs) : 0;
          const label = hoursOver >= 24
            ? `${Math.floor(hoursOver / 24)}d ${Math.floor(hoursOver % 24)}h overdue`
            : `${hoursOver.toFixed(0)} hour(s) overdue`;
          return (
            <Alert
              severity="error"
              icon={<WarningAmberOutlined />}
              sx={{ fontWeight: 600 }}
            >
              <strong>SLA Breached</strong> — This ticket is {label}.
              Deadline was {deadline}.
              {request.escalated_at && ' Priority has been automatically escalated.'}
            </Alert>
          );
        }
        if (hrs !== null && hrs < 24) {
          return (
            <Alert severity="warning" icon={<WarningAmberOutlined />}>
              <strong>SLA Warning</strong> — Only {hrs.toFixed(0)} hour(s) remaining before deadline ({deadline}).
            </Alert>
          );
        }
        if (hrs !== null) {
          const days  = Math.floor(hrs / 24);
          const rem   = Math.floor(hrs % 24);
          const label = days > 0 ? `${days}d ${rem}h` : `${rem}h`;
          return (
            <Alert severity="info" sx={{ py: 0.5 }}>
              SLA deadline: {deadline} — <strong>{label} remaining</strong>
            </Alert>
          );
        }
        return null;
      })()}

      {/* ── AI ANOMALY PANEL ── */}
      {request.ai_anomaly_flagged && request.ai_anomaly_details && request.ai_anomaly_details.length > 0 && (() => {
        const hasHigh   = request.ai_anomaly_details!.some((a) => a.severity === 'high');
        const hasMedium = request.ai_anomaly_details!.some((a) => a.severity === 'medium');
        const severity  = hasHigh ? 'error' : hasMedium ? 'warning' : 'info';
        return (
          <Paper
            variant="outlined"
            sx={{
              borderColor: hasHigh ? '#d32f2f' : hasMedium ? '#ed6c02' : '#0288d1',
              borderRadius: 2, overflow: 'hidden',
            }}
          >
            <Box sx={{
              px: 2.5, py: 1.5,
              bgcolor: hasHigh ? '#fff5f5' : hasMedium ? '#fff8f0' : '#f0f8ff',
              display: 'flex', alignItems: 'center', gap: 1,
            }}>
              <WarningAmberOutlined sx={{ color: hasHigh ? '#d32f2f' : hasMedium ? '#ed6c02' : '#0288d1', fontSize: 20 }} />
              <Box sx={{ flex: 1 }}>
                <Typography variant="body2" fontWeight={700}
                  sx={{ color: hasHigh ? '#d32f2f' : hasMedium ? '#ed6c02' : '#0288d1' }}>
                  AI Anomaly Detection
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {request.ai_anomaly_details!.length} flag(s) were detected when this ticket was submitted
                </Typography>
              </Box>
            </Box>
            <Box sx={{ px: 2.5, py: 1.5 }}>
              <Stack spacing={1}>
                {request.ai_anomaly_details!.map((a, i) => (
                  <Alert
                    key={i}
                    severity={a.severity === 'high' ? 'error' : a.severity === 'medium' ? 'warning' : 'info'}
                    sx={{ py: 0.5, '& .MuiAlert-message': { fontSize: 13 } }}
                  >
                    <strong style={{ textTransform: 'capitalize' }}>{a.type.replace(/_/g, ' ')}</strong>
                    {' — '}
                    {a.message}
                  </Alert>
                ))}
              </Stack>
            </Box>
          </Paper>
        );
      })()}

      {/* ── DEPT MANAGER: approve / reject ── */}      {(canDeptApprove || canDeptReject) && (
        <Alert severity="warning" action={
          <Stack direction="row" spacing={1}>
            <Button size="small" variant="outlined" color="inherit"
              onClick={() => act(() => requestsAPI.deptApprove(Number(id)))}>
              Approve → Send to MIS
            </Button>
            <Button size="small" color="inherit"
              onClick={() => act(() => requestsAPI.deptReject(Number(id)))}>
              Reject
            </Button>
          </Stack>
        }>
          This ticket is waiting for your department approval.
        </Alert>
      )}

      {/* ── MIS MANAGER: assign to officer ── */}
      {canAssign && (
        <Paper sx={{ p: 3 }}>
          <Typography variant="h6" gutterBottom>Assign to MIS Officer</Typography>
          {misUsers.length === 0 ? (
            <Alert severity="warning">
              No active MIS Officers found. Ask an administrator to create MIS Officer accounts first.
            </Alert>
          ) : (
            <Stack spacing={2} sx={{ maxWidth: 420 }}>
              <TextField
                select
                fullWidth
                label="Select MIS Officer"
                value={assignTo || ''}
                onChange={(e) => setAssignTo(Number(e.target.value))}
                helperText="The officer will be able to start working on the ticket immediately after assignment"
              >
                {misUsers.map((u) => (
                  <MenuItem key={u.id} value={u.id}>
                    <Stack>
                      <Typography variant="body2" fontWeight={600}>
                        {u.full_name ?? u.email}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {u.role_name} · {u.email}
                      </Typography>
                    </Stack>
                  </MenuItem>
                ))}
              </TextField>
              <Button
                variant="contained"
                size="large"
                disabled={!assignTo}
                onClick={doAssign}
                sx={{ alignSelf: 'flex-start' }}
              >
                Assign ticket
              </Button>
            </Stack>
          )}
        </Paper>
      )}

      {/* ── MIS OFFICER: start work ── */}
      {canStart && (
        <Alert severity="info" action={
          <Button size="small" color="inherit" variant="outlined"
            onClick={() => act(() => requestsAPI.start(Number(id)))}>
            Start working
          </Button>
        }>
          This ticket is assigned to you. Click to begin.
        </Alert>
      )}

      {/* ── MIS OFFICER: resolve or request clarification ── */}
      {(canResolve || canClarify) && (
        <Paper sx={{ p: 2 }}>
          <Typography variant="h6" gutterBottom>Update ticket status</Typography>
          <Stack direction="row" spacing={2}>
            {canResolve && (
              <Button variant="contained" color="success"
                onClick={() => act(() => requestsAPI.resolve(Number(id)))}>
                Mark as Resolved
              </Button>
            )}
            {canClarify && (
              <Button variant="outlined" color="warning"
                onClick={() => act(() => requestsAPI.requestClarification(Number(id)))}>
                Needs Clarification
              </Button>
            )}
          </Stack>
        </Paper>
      )}

      {/* ── MIS OFFICER: resume after clarification ── */}
      {canResume && (
        <Alert severity="warning" action={
          <Button size="small" color="inherit" variant="outlined"
            onClick={() => act(() => requestsAPI.resume(Number(id)))}>
            Resume working
          </Button>
        }>
          Waiting for the requester's reply. Click to resume once they have responded.
        </Alert>
      )}

      {/* ── REQUESTER: clarification needed notice ── */}
      {isRequester && status === 'Needs Clarification' && (
        <Alert severity="warning">
          The MIS team needs more information. Please reply in the communication thread below.
        </Alert>
      )}

      {/* ── REQUESTER: cancel ── */}
      {canCancel && (
        <Alert severity="info" action={
          <Button size="small" color="inherit"
            onClick={() => act(() => requestsAPI.cancel(Number(id)))}>
            Cancel ticket
          </Button>
        }>
          You can cancel this ticket while it hasn't been assigned to MIS yet.
        </Alert>
      )}

      {/* ── ATTACHMENTS ── */}
      <Paper>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', p: 2 }}>
          <Typography variant="h6">Attachments</Typography>
          <Button component="label" variant="outlined" disabled={uploading}>
            {uploading ? 'Uploading…' : 'Upload file'}
            <input hidden type="file" onChange={upload} />
          </Button>
        </Box>
        <List disablePadding>
          {attachments.map((att) => (
            <ListItem key={att.id}
              secondaryAction={
                <Stack direction="row" spacing={1}>
                  {getFileType(att.file_name) !== 'unsupported' && (
                    <Tooltip title="Preview">
                      <IconButton size="small" onClick={() => openPreview(att)}>
                        <VisibilityOutlined fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  )}
                  <Button size="small" onClick={() => download(att)}>Download</Button>
                </Stack>
              }>
              <ListItemText
                primary={`${att.file_name}${att.is_final ? ' ✓ Final' : ''}`}
                secondary={`v${att.version} · ${new Date(att.created_at).toLocaleString()}`}
              />
            </ListItem>
          ))}
          {!attachments.length && <ListItem><ListItemText primary="No attachments yet" /></ListItem>}
        </List>
      </Paper>

      {/* ── FILE PREVIEW MODAL ── */}
      <Dialog
        open={!!preview}
        onClose={closePreview}
        maxWidth="lg"
        fullWidth
        slotProps={{ paper: { sx: { height: '90vh' } } }}
      >
        <DialogTitle component="div" sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', py: 1.5, borderBottom: '1px solid #e0e0e0' }}>
          <Typography variant="subtitle1" fontWeight={600} noWrap sx={{ maxWidth: '85%' }}>
            {preview?.name}
          </Typography>
          <IconButton size="small" onClick={closePreview}>
            <CloseOutlined />
          </IconButton>
        </DialogTitle>
        <DialogContent sx={{ p: 0, overflow: 'auto' }}>

          {/* Image */}
          {preview?.type === 'image' && (
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', bgcolor: '#1a1a1a', minHeight: '100%', p: 2 }}>
              <Box component="img" src={preview.url} alt={preview.name}
                sx={{ maxWidth: '100%', maxHeight: 'calc(90vh - 80px)', objectFit: 'contain' }} />
            </Box>
          )}

          {/* PDF */}
          {preview?.type === 'pdf' && (
            <Box component="iframe" src={preview.url} title={preview.name}
              sx={{ width: '100%', height: 'calc(90vh - 80px)', border: 'none', display: 'block' }} />
          )}

          {/* Excel / CSV — rendered as HTML table */}
          {preview?.type === 'excel' && preview.sheets && (
            <Box sx={{ p: 2 }}>
              {preview.sheets.map((sheet) => (
                <Box key={sheet.name} sx={{ mb: 3 }}>
                  {preview.sheets!.length > 1 && (
                    <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1, px: 1, py: .5, bgcolor: '#7B1235', color: '#fff', borderRadius: 1, display: 'inline-block' }}>
                      Sheet: {sheet.name}
                    </Typography>
                  )}
                  <Box
                    dangerouslySetInnerHTML={{ __html: sheet.html }}
                    sx={{
                      overflowX: 'auto',
                      '& table': { borderCollapse: 'collapse', width: '100%', fontSize: 13 },
                      '& td, & th': { border: '1px solid #ccc', px: 1.5, py: .75, whiteSpace: 'nowrap' },
                      '& tr:nth-of-type(even)': { bgcolor: '#f9f6f4' },
                      '& tr:first-of-type': { bgcolor: '#7B1235', color: '#fff', fontWeight: 700 },
                    }}
                  />
                </Box>
              ))}
            </Box>
          )}

          {/* Word / DOCX — rendered as HTML */}
          {preview?.type === 'word' && (
            <Box sx={{ maxWidth: 860, mx: 'auto', p: 4 }}>
              <Box
                dangerouslySetInnerHTML={{ __html: preview.html ?? '' }}
                sx={{
                  fontSize: 15, lineHeight: 1.8,
                  '& table': { borderCollapse: 'collapse', width: '100%', mb: 2 },
                  '& td, & th': { border: '1px solid #ccc', px: 1.5, py: .75 },
                  '& h1,& h2,& h3': { color: '#7B1235' },
                }}
              />
            </Box>
          )}

          {/* Plain text / code */}
          {preview?.type === 'text' && (
            <Box component="pre" sx={{ m: 0, p: 3, fontSize: 13, fontFamily: 'monospace', whiteSpace: 'pre-wrap', wordBreak: 'break-word', bgcolor: '#1e1e1e', color: '#d4d4d4', minHeight: '100%' }}>
              {preview.html}
            </Box>
          )}

          {/* Unsupported */}
          {preview?.type === 'unsupported' && (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 200, gap: 2, p: 4 }}>
              <Typography color="text.secondary">This file type cannot be previewed in the browser.</Typography>
              <Typography variant="caption" color="text.secondary">Use the Download button to open it in the appropriate application.</Typography>
            </Box>
          )}

        </DialogContent>
      </Dialog>

      {/* ── COMMUNICATION THREAD ── */}
      <Paper component="form" onSubmit={addComment} sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Typography variant="h6">Communication thread</Typography>
          <List disablePadding>
            {comments.map((c) => (
              <ListItem key={c.id} disableGutters sx={{
                borderLeft: c.is_internal ? '3px solid #e57373' : '3px solid #90caf9',
                pl: 1.5, mb: 1,
              }}>
                <ListItemText
                  primary={c.body}
                  secondary={`${c.is_internal ? '🔒 Internal note' : '💬 Message'} · ${new Date(c.created_at).toLocaleString()}`}
                />
              </ListItem>
            ))}
            {!comments.length && (
              <ListItem disableGutters>
                <ListItemText primary="No messages yet" secondary="Use this thread to communicate with the MIS team." />
              </ListItem>
            )}
          </List>
          <TextField fullWidth multiline minRows={2} label="Write a message"
            value={commentText} onChange={(e) => setCommentText(e.target.value)} />
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            {isMIS && (
              <FormControlLabel
                control={<Checkbox checked={internal} onChange={(e) => setInternal(e.target.checked)} />}
                label="Internal note (not visible to requester)"
              />
            )}
            <Button type="submit" variant="contained" disabled={!commentText.trim()} sx={{ ml: 'auto' }}>
              Send
            </Button>
          </Box>
        </Stack>
      </Paper>

      {/* ── FEEDBACK FORM (requester, after Resolved) ── */}
      {canFeedback && (
        <Paper component="form" onSubmit={submitFeedback} sx={{ p: 2 }}>
          <Stack spacing={2}>
            <Typography variant="h6">Rate your experience</Typography>
            <Typography variant="body2" color="text.secondary">
              Your ticket has been resolved. Please rate the service before it is closed.
            </Typography>
            <Box>
              <Typography component="legend">Report quality</Typography>
              <Rating value={quality} onChange={(_, v) => setQuality(v ?? 0)} />
            </Box>
            <Box>
              <Typography component="legend">Timeliness</Typography>
              <Rating value={timeliness} onChange={(_, v) => setTimeliness(v ?? 0)} />
            </Box>
            <TextField label="Additional comments (optional)" multiline minRows={2}
              value={feedbackNote} onChange={(e) => setFeedbackNote(e.target.value)} />
            <Button type="submit" variant="contained" disabled={!quality || !timeliness}>
              Submit feedback &amp; close ticket
            </Button>
          </Stack>
        </Paper>
      )}

      {/* feedback already submitted */}
      {feedback && (
        <Alert severity="success">
          Feedback submitted — Quality: {feedback.quality_rating}★ · Timeliness: {feedback.timeliness_rating}★
          {feedback.comment && ` · "${feedback.comment}"`}
        </Alert>
      )}
    </Stack>
  );
}
