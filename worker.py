def worker(xmpp, q):
  while True:
    data, jid, title = q.get()
    if data is None and jid is None and title is None:
      break
    bare_jid = jid.split('/')[0].lower()

    q.task_done()
