gql_mutation_create_ticket = """
mutation createTicket {
  createTicket(input: {
    category: "%s",
    title: "%s",
    description: "%s",
    resolution: "%s",
    priority: "%s",
    dateOfIncident: "%s",
    channel: "%s",
    flags: "%s",
    clientMutationId: "%s"
  }) {
    clientMutationId
  }
}
"""


gql_mutation_update_ticket = """
mutation updateTicket {
  updateTicket(input: {
    id: "%s",
    category: "%s",
    title: "%s",
    resolution: "%s",
    priority: "%s",
    dateOfIncident: "%s",
    channel: "%s",
    flags: "%s",
    status: %s,
    clientMutationId: "%s"
  }) {
    clientMutationId
  }
}
"""


gql_mutation_create_comment = """
mutation createComment {
  createComment(input: {
    comment: "%s",
    ticketId: "%s",
    commenterId: "%s",
    commenterType: "%s",
    clientMutationId: "%s"
  }) {
    clientMutationId
  }
}
"""


gql_mutation_create_comment_anonymous_user = """
mutation createComment {
  createComment(input: {
    comment: "%s",
    ticketId: "%s",
    clientMutationId: "%s"
  }) {
    clientMutationId
  }
}
"""


gql_mutation_resolve_ticket_by_comment = """
mutation resolveGrievanceByComment {
  resolveGrievanceByComment(input: {
    id: "%s",
    clientMutationId: "%s"
  }) {
    clientMutationId
  }
}
"""

gql_mutation_close_ticket = """
mutation closeTicket {
  closeTicket(input: {
    id: "%s",
    category: "%s",
    title: "%s",
    resolution: "%s",
    priority: "%s",
    dateOfIncident: "%s",
    channel: "%s",
    flags: "%s",
    comment: "%s",
    clientMutationId: "%s"
  }) {
    clientMutationId
  }
}
"""

gql_mutation_close_ticket_by_user = """
mutation closeTicket {
  closeTicket(input: {
    id: "%s",
    category: "%s",
    title: "%s",
    resolution: "%s",
    priority: "%s",
    dateOfIncident: "%s",
    channel: "%s",
    flags: "%s",
    commenterType: "user",
    commenterId: "%s",
    comment: "%s",
    clientMutationId: "%s"
  }) {
    clientMutationId
  }
}
"""

gql_mutation_reopen_ticket = """
mutation reopenTicket {
  reopenTicket(input: {
    id: "%s",
    clientMutationId: "%s"
  }) {
    clientMutationId
  }
}
"""
