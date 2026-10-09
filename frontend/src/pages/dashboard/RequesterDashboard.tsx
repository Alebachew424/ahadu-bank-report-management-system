/**
 * Overview page — adapts based on role:
 *   MIS Manager / Supervisor / Admin → PerformanceDashboard
 *   Everyone else                    → personal ticket overview
 */
import { useEffect, useState } from 'react';
import {
  Alert, Box, Button, Chip, CircularProgress,
  InputAdornment, List, ListItem, ListItemButton,
  ListItemText, Paper, Stack, TextField, Typography,
} from '@mui/material';
import { Add, SearchOutlined } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { requestsAPI } from '../../api/requests';
import { authAPI } from '../../api/auth';
import { PerformanceDashboard } from './PerformanceDashboard';
import type { ReportRequest } from '../../types/types';

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

export function RequesterDashboard() {
  const navigate = useNavigate();
  const [requests, setRequests] = useState<ReportRequest[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState('');
  const [search,   setSearch]   = useState('');
  const [roleName, setRoleName] = useState('');
  const [roleLoading, setRoleLoading] = useState(true);

  useEffect(() => {
    authAPI.me()
      .then((r) => setRoleName(r.data.role_name))
      .catch(() => undefined)
      .finally(() => setRoleLoading(false));

    requestsAPI.list()
      .then((r) => setRequests(r.data))
      .catch(() => setError('Unable to load your tickets'))
      .finally(() => setLoading(false));
  }, []);

  if (roleLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', pt: 8 }}><CircularProgress /></Box>;

  // MIS managers see the performance dashboard
  if (MIS_MANAGER_ROLES.includes(roleName)) return <PerformanceDashboard />;

  // Everyone else sees their personal ticket list
  const terminal   = ['Closed', 'Resolved', 'Rejected', 'Cancelled'];
  const openCount  = requests.filter((r) => !terminal.includes(r.status_name ?? '')).length;
  const closedCount= requests.filter((r) => ['Closed','Resolved'].includes(r.status_name ?? '')).length;
  const pendingCount= requests.filter((r) => ['Pending Dept Approval','Needs Clarification'].includes(r.status_name ?? '')).length;

  const filtered = requests.filter((r) => {
    const q = search.toLowerCase();
    return !q || r.title.toLowerCase().includes(q) || String(r.id).includes(q) || (r.status_name ?? '').toLowerCase().includes(q);
  });

  return (
    <Stack spacing={3}>
      {/* header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 2 }}>
        <Box>
          <Typography variant="h5" fontWeight={700}>My Tickets</Typography>
          <Typography variant="body2" color="text.secondary">
            Track your report requests and communicate with the MIS team.
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<Add />}
          onClick={() => navigate('/requests/create')}
          sx={{ bgcolor: '#7B1235', '&:hover': { bgcolor: '#5f0d29' } }}
        >
          New request
        </Button>
      </Box>

      {error && <Alert severity="error">{error}</Alert>}

      {/* stat cards */}
      <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
        {[
          { label: 'Open tickets',   value: openCount,    color: '#7B1235' },
          { label: 'Total submitted',value: requests.length, color: '#a06b32' },
          { label: 'Closed',         value: closedCount,  color: '#2e6b57' },
          { label: 'Needs attention',value: pendingCount, color: '#b85c00' },
        ].map((s) => (
          <Paper key={s.label} sx={{ px: 2.5, py: 1.5, borderTop: `3px solid ${s.color}`, flex: 1, minWidth: 130 }}>
            <Typography variant="caption" sx={{ color: s.color, fontWeight: 700, fontSize: 10, letterSpacing: .6, textTransform: 'uppercase' }}>
              {s.label}
            </Typography>
            <Typography sx={{ fontSize: 30, fontWeight: 800, color: s.color, lineHeight: 1.1 }}>{s.value}</Typography>
          </Paper>
        ))}
      </Box>

      {/* search */}
      <Paper sx={{ p: 2 }}>
        <TextField
          fullWidth
          size="small"
          placeholder="Search by title, ticket ID or status…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchOutlined fontSize="small" sx={{ color: '#7B1235' }} />
                </InputAdornment>
              ),
            },
          }}
        />
        {search && (
          <Typography variant="caption" color="text.secondary" sx={{ mt: .5, display: 'block' }}>
            {filtered.length} of {requests.length} tickets
          </Typography>
        )}
      </Paper>

      {/* ticket list */}
      <Paper>
        <Box sx={{ px: 2.5, py: 1.5, borderBottom: '1px solid #e6e0dc' }}>
          <Typography variant="h6" fontWeight={700}>Recent tickets</Typography>
        </Box>
        <List disablePadding>
          {loading && (
            <ListItem><ListItemText primary="Loading…" /></ListItem>
          )}
          {!loading && filtered.map((r) => (
            <ListItem key={r.id} disablePadding sx={{ borderBottom: '1px solid #f2eded' }}>
              <ListItemButton onClick={() => navigate(`/requests/${r.id}`)} sx={{ py: 1.5, px: 2.5 }}>
                <ListItemText
                  primary={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Typography variant="body2" fontWeight={600}>{r.title}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        #{String(r.id).padStart(5, '0')}
                      </Typography>
                    </Box>
                  }
                  secondary={`Due ${new Date(r.due_date).toLocaleDateString()} · ${r.priority} priority`}
                />
                <Chip
                  size="small"
                  label={r.status_name ?? `Status ${r.status_id}`}
                  color={STATUS_COLOUR[r.status_name ?? ''] ?? 'default'}
                  sx={{ fontWeight: 600, fontSize: 11 }}
                />
              </ListItemButton>
            </ListItem>
          ))}
          {!loading && filtered.length === 0 && !error && (
            <ListItem sx={{ py: 4, justifyContent: 'center' }}>
              <ListItemText
                sx={{ textAlign: 'center' }}
                primary={search ? 'No tickets match your search.' : 'No tickets yet.'}
                secondary={!search ? 'Click "New request" to submit your first ticket.' : undefined}
              />
            </ListItem>
          )}
        </List>
      </Paper>
    </Stack>
  );
}
