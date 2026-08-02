# Controlled CRM-to-support handoff

## Problem

A won CRM relationship should become usable support context without an operator
manually recreating the company and customer identity in Zendesk. Manual copying
can produce incomplete records, duplicate customers, mismatched organizations,
and untraceable field changes.

## Implementation

The control plane validates one approved won relationship, produces deterministic
HubSpot and Zendesk payloads, sequences the organization before the end user, and
reconciles both provider readbacks against one handoff key.

The verified controlled run contained one HubSpot company, one contact, one
closed-won deal, three native associations, one Zendesk organization, and one
linked end user. A second run reused the existing records.

## Failure handling

The workflow blocks unapproved relationships, non-won deals, incomplete required
fields, provider-visible test labels, duplicate external IDs, incorrect Zendesk
membership, and incomplete HubSpot associations.

## Public boundary

The implementation uses synthetic records and proves provider-backed mapping,
readback, and replay controls. It does not prove production adoption, customer
communication, ticket automation, AI, Jira, or business outcomes.

