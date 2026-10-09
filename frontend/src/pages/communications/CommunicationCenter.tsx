import { ChatBubbleOutlined, Search } from '@mui/icons-material';
import { Alert, Button, InputAdornment, Paper, Stack, TextField, Typography } from '@mui/material';

export function CommunicationCenter() {
  return (
    <Stack spacing={2}>
      <div>
        <Typography variant="h4">Communications</Typography>
        <Typography color="text.secondary">Coordinate updates and follow up on active report tickets.</Typography>
      </div>
      <Paper sx={{ p: 2 }}>
        <TextField fullWidth placeholder="Search ticket conversations" slotProps={{ input: { startAdornment: <InputAdornment position="start"><Search /></InputAdornment> } }} />
      </Paper>
      <Alert icon={<ChatBubbleOutlined />} severity="info" action={<Button color="inherit" size="small" href="/requests">OPEN QUEUE</Button>}>
        Ticket conversations appear here when internal notes and requester messages are enabled for a request.
      </Alert>
    </Stack>
  );
}