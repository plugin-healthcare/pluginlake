# ViscoSuite and pluginlake: architectural discussion

**Date:** 2026-07-16
**Participants:** @yannick-vinkesteijn
**Topic:** Evaluating a collaboration with ViscoSuite and how it would fit into pluginlake.
**Status:** Exploratory. No concrete pipeline committed. Most design points are settled (also stored as repository memories); a few remain open.

## TL;DR

- ViscoSuite is an upstream integration engine (Frank!Framework, JVM) plus an operational FHIR CDR (HAPI). Its job is turning messy HL7v2 and XML into FHIR; it sits on the ingestion edge, before pluginlake.
- Recommended boundary: all HL7v2 and XML/XSLT transformation stays behind the edge in ViscoLink; the only contract to pluginlake is FHIR JSON (NDJSON). No XML reaches our Python code, so the XML-parsing worry never lands on us.
- No tool overlap with Dagster: Frank! is message-level integration at the edge, Dagster is our batch orchestrator inside the lakehouse. They meet at the FHIR-NDJSON handoff, not in the same layer.
- Lean default: adopt ViscoLink as a stateless transform edge and stream FHIR into pluginlake; defer ViscoStore (the operational FHIR CDR) unless a concrete FHIR-out consumer appears.
- Ingestion path: source, broker (streaming landing zone), landing zone raw dump, Dagster readability gate, bronze (first governed FHIR NDJSON), silver (FHIR CDM), gold (curated serving products: OMOP for analytics today, an optional curated FHIR mart if FHIR-out is ever needed). The lakehouse OLAP engine (DuckLake) never sits on the hot arrival path.
- Streaming safety: Dagster is triggered on cadence or threshold, never per event, so a high-volume burst is absorbed by the broker and raw dump instead of overwhelming the orchestrator.
- Deferred: real-time analytics and serving is a separate future workstream; pluginlake's composable design lets it be added later by substituting individual components, without redoing the batch plane.

## Purpose

A record of the discussion, each point with its conclusion, so the reasoning is preserved and can feed future ADRs.

## System under evaluation

ViscoSuite, hosted at https://git.viscosiety.com/public-applications/viscosuite/.

---

## 1. What is ViscoSuite?

A self-hosted, JVM-based healthcare integration platform. Three Maven modules, all run as WARs inside one Tomcat instance.

- **ViscoLink**: a Frank!Framework integration layer. Receives HL7v2 (MLLP and HTTP), FHIR, and REST from source systems, validates and transforms via XSLT pipelines, and routes results to ViscoStore. Stateless; configuration lives as XML files mounted into the container, so no rebuild is needed to add integrations.
- **ViscoStore**: a HAPI FHIR JPA Server (Postgres-backed). An operational FHIR repository (a CDR). Exposes a FHIR REST API, a tester UI, Swagger, and an MCP endpoint for AI/LLM access.
- **ViscoRunner**: Docker and Tomcat packaging.

**Conversions actually shipped (verified against the cloned repo).**

The custom pipes are `Hl7v2ToXmlPipe`, `XmlToHl7v2Pipe`, and `FhirValidatorPipe` (validation, not conversion). On top of those the six demo configurations cover:

| Conversion | Direction | Read/write |
|---|---|---|
| HL7v2 pipe-delimited ↔ HL7v2 XML | both ways | read and write (`XmlToHl7v2Pipe` emits pipe-delimited for MLLP send / ACK) |
| HL7v2 ADT (A01–A13) / SIU (S12–S15) → FHIR R4 Bundle | inbound only | write into ViscoStore, via per-message XSLT |
| HL7v2 → structured XML | inbound | read/inspect preprocessing step |
| FHIR ↔ FHIR across R4 / DSTU3 / R5 | facade | read from ViscoStore and serve transformed FHIR |
| Postgres fake-EMR → FHIR Bundle | source pull | write |
| LOINC enrichment of FHIR Observations | in-flight | read-only (no writeback) |

So the flow is bidirectional at the HL7v2 encoding level and read-and-write overall (ingest writes FHIR into ViscoStore; facades/proxy/enrichment read from it and serve FHIR out), but the clinical translation demonstrated is normalization *into* FHIR. No FHIR → HL7v2 clinical mapping ships, though `XmlToHl7v2Pipe` is the primitive to build one.

**OMOP converter: claimed but absent.** Despite a verbal claim of an OMOP converter, there is zero OMOP anywhere in the open repo (paths or file contents). No OMOP pipe, config, XSLT, or vocabulary mapping. The only terminology handled is LOINC, and only as query-time enrichment, not a format converter. No CDA/C-CDA, DICOM, X12, or SNOMED/ICD either. OMOP is exactly pluginlake's gold-serving concern, so if ViscoSuite ever adds it that would overlap our tier, unlike the clean upstream HL7v2 → FHIR edge. Clone kept at `/home/yannick/code/viscosuite` for later checking.

**Runtime shape.**

ViscoLink is stateless (it retains nothing between messages) but runs as a long-lived, always-on service, not a spawn-per-event function.
A persistent MLLP socket listener has to stay up to receive HL7 feeds, and JVM warm-up makes per-message spawning impractical, so the process is always on.
Statelessness is what lets it scale horizontally: run multiple replicas behind a load balancer, since any replica can handle any message (a Deployment with N replicas, not a Job or scale-to-zero function).
Individual Frank! flows can opt into state deliberately (an error store, a retry or JMS queue, an idempotency ledger); the default transform path is stateless.

**Conclusion:** ViscoSuite is an integration engine (ESB or Mirth class) plus an operational FHIR CDR. Its job is normalizing messy source data into FHIR. It sits upstream of pluginlake, on the ingestion edge.

## 2. What does Frank!Framework do?

The first read was "an orchestrator and connector", which made it look like it overlaps with Dagster and our connectors.

Frank!Framework is a message-driven integration engine (an ESB-lite built on Java and Spring, formerly IAF). Its parts show up throughout the ViscoSuite code:

- **Adapter**: one integration flow.
- **Listener / Receiver**: how a message arrives (MllpListener for HL7v2 over TCP, ApiListener for HTTP, FhirListener, JMS, DB poller).
- **Pipeline**: an ordered chain of Pipes, with named forwards for routing.
- **Pipe**: one step (XsltPipe transform, FhirValidatorPipe, PutInSessionPipe, a switch, a sender call).
- **Sender**: how it calls out (MllpSender, HTTP, JDBC).
- **Ladybug**: records each pipe input and output per message for trace, replay, and debug.

Conclusion: Frank! orchestrates messages (real-time, per-event, stateless), not data assets. Its "connectors" are protocol adapters (MLLP, HL7v2, FHIR REST, JMS), not data-source backends. It does not compete with Dagster; it is an upstream tier that feeds it.

## 3. How their tools relate to ours (Dagster, connectors)

Both "orchestrate" and both "connect", but the words are overloaded and the tiers differ.

| Aspect | Frank! (ViscoLink) | Dagster |
|---|---|---|
| Unit of work | a single message / event | a data asset / batch job |
| "Orchestration" means | routing one message through pipeline pipes | a DAG of dataset dependencies, retries, partitions, lineage |
| "Connectors" means | protocol adapters (MLLP, HL7v2, FHIR REST) | data-source backends (DuckDB, files, object store) |
| Trigger | message arrival (real-time) | schedule, sensor, or manual (batch) |
| Latency | milliseconds, synchronous | seconds to hours, async |
| State | stateless, persists nothing | materializes durable tables, tracks lineage |
| Analogy | Mirth, Apache Camel, ESB | Airflow, Prefect |

Conclusion: They do not substitute for each other. Dagster cannot terminate an MLLP socket and return a synchronous ACK; Frank! has no materialized datasets, asset DAG, or lineage. Frank! owns the real-time ingestion edge, Dagster owns batch analytics.

## 4. XML parsing cost and where it belongs

Concern: ViscoSuite produces and parses a lot of XML, and XML parsing is expensive, particularly in Python.

Where the XML lives.
The XML (Frank! configuration, XSLT stylesheets, HL7v2-XML encoding) stays inside ViscoLink.
If the handoff to pluginlake is FHIR JSON NDJSON, pluginlake never sees or parses XML.
Verified: pluginlake has no HL7, XML, XSLT, MLLP, or bulk-export code today.

The parsing-cost question, in context.
The concern is valid: XML is genuinely one of the heavier formats to parse, and the naive approach makes it worse.
Two points refine it:

- It is a parsing-model problem, not only a format problem.
  A DOM parser reads the whole document into an in-memory tree (high memory, slow); a streaming parser walks the document as an event stream and holds only the current element (bounded, constant memory).
  Streaming XML parsers are a mature, decades-old standard: SAX and StAX on the JVM, `XmlReader` in .NET, `encoding/xml` in Go, `lxml.iterparse` in Python.
  Most are bindings over the same two C engines (expat, libxml2).
- Absolute cost is very language-dependent.
  XML parsing is costly everywhere, but the penalty is far smaller on the JVM and in C/Go/Rust than in pure-Python.
  Python's fast path (lxml) is itself a libxml2 (C) binding; naive `xml.etree` is what earns XML its bad reputation in Python.
  ViscoLink parses small per-message HL7/FHIR documents (kilobytes each) on the JVM with Saxon, which is well within its comfort zone.

So the workload matters as much as the format: a small message streamed on the JVM is cheap, a multi-gigabyte document DOM-parsed in pure-Python is not.

Why we still prefer JSON NDJSON regardless.
Even at its best, XML sits low in the format hierarchy: columnar binary (Parquet/Arrow) is fastest, then NDJSON, then plain JSON, then streaming XML, with DOM XML last.
NDJSON's decisive advantage for a lakehouse is that it is splittable: one record per line means files can be chunked at newline boundaries and parsed shards in parallel, which XML cannot do cleanly.
So NDJSON wins on both throughput and parallelism, in any language.

Residual concern.
The remaining issue is XSLT maintainability and specialist skills, which sits with the edge owner (a Frank! specialist partner's strength) and never reaches our Python codebase.

Conclusion: Keep the boundary at FHIR JSON NDJSON so XML stays behind the edge, and pin the contract to JSON serialization so no XML-serialized FHIR reaches us.

## 5. Duplicate places of processing

Concern: transformation happening in two places.

There are two transform stages, and they do different jobs:

- HL7v2 to FHIR belongs in ViscoLink (XSLT). Not in pluginlake.
- FHIR to OMOP belongs in plugin-rosetta (Python). Not in Frank! XSLT.

Overlaps to decide on purpose:

- FHIR is not inherently stored twice. In the lean default (ViscoStore deferred, see TL;DR), FHIR is only a transport format: ViscoLink transforms and streams it straight into pluginlake's landing zone, and pluginlake's DuckLake `fhir_raw` is the single stored copy. A second stored copy exists only if ViscoStore (the operational CDR) is actually deployed for a FHIR-out consumer, and then it is a deliberate operational-versus-analytical split, not accidental duplication.
- Two different meanings of "FHIR" must be kept apart, because ViscoSuite and pluginlake use it for different jobs:
  - FHIR for technical read/validation: is this well-formed, legal FHIR (has `resourceType`, parses)? This is all the transport contract and pluginlake's bronze gate assert. ViscoSuite deliberately leans on FHIR's extension flexibility to carry new fields without conforming to a strict analytical model like OMOP, so at the seam FHIR is a loose, extensible envelope, not a conformed schema.
  - FHIR as a common data model: do the fields plugin-rosetta needs conform to the FHIR CDM? This is a stronger assertion, bound later at pluginlake silver (see point 6), and it is where the extension-carried extras either map into the model or are parked.
- FHIR validation depth therefore differs on each side by design (see point 6), matching these two meanings.

Conclusion: No transform lives in two places. Any overlap is intentional and conditional: a second FHIR copy exists only if ViscoStore is deployed, and validation is layered by the two meanings of FHIR above, not accidental duplication.

## 6. Validation responsibilities and late binding

This was the main question. The resolution: split validation by what is asserted, not by technology, and lean on late binding.

pluginlake follows a medallion model with late binding: land the minimum each layer needs, defer meaning downstream.

| Layer | What it asserts | Failure mode | Owner |
|---|---|---|---|
| ViscoLink (source edge) | strong FHIR conformance (HAPI profile validation) | reject synchronously back to the source system | ViscoSuite |
| pluginlake landing zone (raw dump) | nothing; durable drop-off of exactly what arrived (raw files or blobs, opaque, unvalidated) | none here; the bronze gate decides pass or reject | pluginlake |
| pluginlake bronze | technically readable, legal FHIR (well-formed, has resourceType) | reject-to-source plus dead-letter; promote the rest | pluginlake |
| pluginlake silver | conforms to the FHIR common data model (fields plugin-rosetta needs), and runs the standard structural FHIR→OMOP CDM mapping (`fhir_omop_raw`) | flag, do not block the raw landing | pluginlake |
| pluginlake gold | curated serving products built on silver; for OMOP that means terminology/vocabulary resolution, selection and size-limiting into a consumption-ready analytics product | vocabulary_validation, already built | pluginlake |

Key points:

- Bronze answers "can our systems read and pick this up, so we can catalogue and govern it?", silver answers "do we understand the content well enough to conform it and transform it into other standards?" (for FHIR that means meeting the common data model, and it is also where the reusable structural FHIR→OMOP CDM mapping runs, producing `fhir_omop_raw`), gold answers "is this a curated, consumption-ready product?" (for the OMOP product, terminology/vocabulary resolution plus curation on top of the silver OMOP tables). No layer redoes another's work.
- FHIR→OMOP is not a gold/end table by itself. The structural mapping is a widely-available, reusable pipeline transform (plugin-rosetta) and belongs in silver alongside FHIR CDM conformance; gold is only the curated, terminology-resolved, size-limited serving product materialized from it.
- Gold is the curated serving tier, not a single fixed model. It materializes consumption-ready products in whatever standard a consumer needs: OMOP plus terminology for analytics today, an optional curated FHIR mart for FHIR-out (see point 11), and room for others later. pluginlake is standards-open by design, so gold is not OMOP-locked.
- pluginlake's bronze gate is producer-agnostic: it applies whether the FHIR came from ViscoSuite or a raw NDJSON drop, so it is not coupled to or duplicating ViscoLink.
- Correction to an earlier framing ("trust the edge, do not re-validate"): pluginlake runs its own light readability gate at its own trust boundary. Late binding is why it does not run heavy conformance at the door.
- Current gap: `fhir/loader.py` only checks that a line is valid JSON, not that it is legal FHIR, and it silently drops invalid lines. A real bronze gate would check resourceType, optionally parse against the plugin-rosetta datamodel in non-strict mode, and quarantine rejects (auditable) instead of dropping them.

Conclusion: ViscoLink's strong conformance and pluginlake's bronze readability are different-strength checks at different boundaries with different failure modes, so they are not duplication. Medallion plus late binding settles the duplicate-validation question.

## 7. Representation binding versus analytical binding

Why converting to FHIR at the edge is not an early-binding violation.

- Representation binding (HL7v2 to FHIR): normalize the messy wire format to a canonical clinical model. This belongs at the edge, because HL7v2 is a positional, version-quirky, real-time protocol that only the integration engine should touch. Raw HL7v2 is a poor lake format.
- Analytical binding (FHIR to OMOP plus terminology): the opinionated modeling. Deferred to pluginlake silver and gold.

Conclusion: FHIR is the right seam. It is the earliest point where the data is self-describing, JSON-native, and analytics-friendly without committing to an analytical model.

## 8. Single canonical ingestion format

pluginlake accepts one format in: FHIR R4 JSON NDJSON, one resourceType per file. This matches the existing `POST /api/v1/fhir/{resource_type}/ndjson` endpoint and the folder-watch sensor.

Accepting multiple formats would mean N parsers, N readability gates, N quarantine paths, and N schema drifts, which is the duplicate-processing anti-pattern. Any other or output shape (a different CDM, an export, HL7v2 regenerated for a downstream system) is produced on demand, either as a Dagster batch transform from landed data or back at ViscoLink (which has XmlToHl7v2Pipe). Format fan-out is the edge's job or an on-demand batch job, not a standing ingestion concern.

Contract details to pin:

- FHIR R4 (not R5 or DSTU3): ViscoStore supports all three, but plugin-rosetta is R4. Lock the export to R4 or translation breaks.
- JSON serialization (not XML), NDJSON framing, per-resourceType files.
- Lossy mapping is acceptable: the lake is an analytical copy, and the raw source of truth lives in ViscoStore and the origin EHR. If a dropped field matters later, fix it in ViscoLink's XSLT, not in pluginlake.

Conclusion: One canonical format in (FHIR R4 JSON NDJSON), transform on demand for everything else. That is YAGNI plus late binding.

## 9. Real-time and streaming ingestion

Requirement: pluginlake should be able to receive real-time or streaming data, handled outside Dagster, landing to the lake.

Pattern:

```
real-time source
  -> streaming ingest service (standing, OUTSIDE Dagster): a broker buffers the arrival burst
  -> landing zone = raw dump (raw files/blobs as received; opaque; unvalidated; NOT a lakehouse table)
  -> Dagster readability gate (triggered on a cadence/threshold, never per event):
       pass -> bronze ; malformed -> reject-to-source + dead-letter
  -> bronze (first governed lakehouse table: trusted FHIR NDJSON) -> silver -> gold
```

- Dagster stays batch. The standing ingestion service (any language) owns the real-time source and drops raw events into the landing zone; Dagster starts at the readability gate that promotes the landing zone into bronze.
- The landing zone is a raw dump, not a table: raw files/blobs in object storage as received (opaque, unvalidated, schema-free). The lakehouse (governed tables) begins at bronze, after the gate. A raw dump keeps ingestion dumb and cheap; the tradeoff is that replay, dedup, and cleanup use object keys plus a cursor and a retention policy, not table time-travel.
- Decouple arrival from Dagster so high volume does not make Dagster go wild. The streaming lane of the landing zone is buffered by a broker that absorbs the burst; Dagster is triggered on a cadence or threshold (interval sensor plus cursor, or N records or T seconds) and drains the backlog in one controlled micro-batch, never per event. Backpressure lets the broker hold the backlog if Dagster falls behind, and promoting in batches consolidates many small raw-dump files into fewer bronze Parquet files. The landing zone has two lanes: a batch/bulk lane (discrete `$export` or folder-watch drops, picked up per file) and a streaming lane (broker-buffered, rate-controlled).
- OLTP versus OLAP: keep the fast path off the slow engine. DuckLake is not a streaming sink (it is DuckDB plus Parquet snapshots); lake materialization is micro-batch, not sub-second. Streaming velocity is absorbed by the broker and the raw dump write, both fast and OLAP-free; only the async batch promotion touches DuckLake, on a cadence. This is exactly why the landing zone is a raw dump and not a DuckLake table: a per-event table insert would be the mistake of forcing a fast stream through a slow OLAP engine. The lake does real-time ingest (queryable within a micro-batch), not real-time serving. Sub-second reads on live data (true OLTP) belong to a separate serving layer or ViscoStore, never the lake; sub-second streaming analytics would be a real-time OLAP or stream processor (Flink, ClickHouse, Druid, Materialize), a different engine class and likely YAGNI here.
- Format is still canonical FHIR NDJSON. The FHIR-native real-time option is FHIR Subscriptions (ViscoStore pushes changed resources); the batch option is Bulk `$export`. A broker (RabbitMQ, already in the ViscoSuite demo, or Kafka or NATS) suits higher volume, backpressure, and replay.
- Security: the streaming ingress is a second ingestion enforcement point (source-side authn plus the bronze gate). It does not bypass the consumer-side PEP.
- Composable stack: the streaming service writes via the shared framework-agnostic StorageBackend, not a Dagster resource, matching the data-connectors architecture.

Conclusion: A standing service outside Dagster drops raw events into the landing zone (a raw dump, broker-buffered on the streaming lane); Dagster's readability gate promotes the landing zone into bronze on a cadence or threshold, not per event, so high volume never makes Dagster go wild. Lake materialization stays micro-batch.

## 10. Deployment topology and security (partially discussed, to finalize)

Grounded in ADR-005 (FastAPI gateway) and ADR-008 (Dataspace Protocol, authn, authz).

Security invariants (ADR-008):

- Single enforcement point (PEP): no request reaches station compute except through one mandatory authn and authz enforcer.
- Network perimeter: the station cluster and its services are isolated; only curated endpoints are reachable; internal services (Nuts node, Postgres, Dagster) are never directly reachable from outside.
- Transport independence: if FastAPI is replaced by a leaner protocol or mesh, enforcement stays in the proxy or sidecar.
- Layer separation: Nuts governs machine-to-machine membership and coarse roles (hub, analytics, ml); fine-grained, user-based, contract-scoped access is a separate ODRL layer on top.

The data flow has two hops, each its own boundary.

Hop 1, conduit to ViscoLink. A conduit in the hospital hooks into the EPD and feeds ViscoLink over its inbound listeners (MLLP on 2575, or HTTP for HL7v2/FHIR/REST). ViscoLink normalizes to FHIR. Important: ViscoSuite ships these as raw servlet endpoints on plain HTTP and does not ship an auth layer or hardened gateway for its API; the repo itself says to put a reverse proxy (nginx/traefik) in front for TLS. So the endpoints are reachable by default, but securing that channel (TLS, auth, network restriction) is the deployer's job, not something ViscoSuite provides.

Hop 2, ViscoLink to the station. ViscoLink lands FHIR NDJSON into the station's landing zone. This crosses the data station border into station compute, so by the PEP invariant it goes through the station's credentialed ingestion endpoint like any other producer, not a direct write. ViscoLink is not a federation participant (no Nuts network identity, no DSP surface); it is just a credentialed client of the ingestion endpoint.

Known gap. We have not defined an authn/authz flow for services that sit outside a station but inside the same organization (for example ViscoLink on a neighbouring cluster). The ADRs so far cover only the org-to-org federation plane (hub↔station, user↔hub via DSP, Nuts, ODRL). This same-org, cross-station-border case still needs to be described, likely in its own ADR: what credential the producer presents, whether it reuses the FastAPI PEP or a dedicated ingestion endpoint, and how producers are registered.

Topology options considered:

- A. Optional private module co-deployed inside the plugin data-station cluster (docker compose or Kubernetes). Preferred. Its only inbound surface is the source-facing intake (the conduit from hospital source systems), and its only egress is landing FHIR NDJSON through the station's ingestion PEP, where it authenticates like any other producer. Because it lives inside the station's own trust domain it is not a federation participant and needs no Nuts network identity, but it still crosses the station border under credential checks. The one real risk, that ViscoLink parses untrusted messy HL7v2/XML, is contained with internal network segmentation (own namespace and network policy, Frank!Console and MCP locked down) rather than by promoting it to an external service.
- B. Separate integration cluster or machine. Possible but not preferred. Putting ViscoLink on its own cluster pushes it across a network boundary where, to stay consistent with the ADRs, it risks being treated as an external or hybrid node, forcing its own Nuts node, identity, and authn/authz. That is significant overhead for a service that only lands data. The blast-radius isolation this buys can instead be achieved with in-cluster segmentation (option A).
- C. Dagster-orchestrated pull for the `$export` handoff: valid for batch, but the ViscoLink real-time listener must be a standing service, not a Dagster op.

Proposed conclusion (open): prefer option A. ViscoLink runs as a private in-cluster module, exposes only the conduit intake to the hospital source (TLS and auth added by the deployer), and lands FHIR NDJSON through the station's ingestion PEP. FastAPI stays the single consumer PEP; ViscoLink adds no consumer ingress. Still open: the same-org ingestion credential and endpoint (see the gap above).

## 11. Do we need a FHIR server, and if so where?

Question: instead of a full HAPI or Firely FHIR server, could pluginlake expose a thin FHIR façade over its own DuckDB and Polars compute?

Why not by default. DuckDB and Polars are OLAP (analytical) engines; a real FHIR server is OLTP (point reads, per-resource search, writes, transactions, plus the parts that make FHIR hard: the full search framework with chaining, `_include`/`_revinclude`, paging, `$validate`, terminology ops, Subscriptions, SMART-on-FHIR). A façade over DuckLake only covers a narrow read-only query set (like ViscoSuite's loinc-enriched façade); beyond that you reimplement HAPI. pluginlake is analytical: consumers query OMOP through DSP, not live FHIR. So for ingest-FHIR, serve-OMOP it needs neither ViscoStore nor a rich façade.

When and where you would add one. Only if a real operational FHIR-out consumer appears. Then it is a small, bounded, rebuildable serving projection over curated gold, never the system of record or ingestion sink (DuckLake stays SoR). Project it from the FHIR side (silver to a curated FHIR gold mart), not by round-tripping OMOP to FHIR, which is lossy. That yields two parallel gold surfaces from one silver: OMOP gold for analytics and an optional curated FHIR gold for FHIR-out. Keep the slice small so it stays under HAPI/Firely's scaling ceiling; at analytical scale prefer lake-native SQL-on-FHIR (Pathling, the ViewDefinition spec, Bulk `$export` straight from the lake). Because bronze is already FHIR, the seam is always there, so defer until a concrete consumer exists and build only over the slice they need.

Build versus buy. Do not build the hard part of a FHIR server, the search framework (search params, chaining and reverse chaining, `_include`/`_revinclude`, modifiers, paging); use an existing server or the SQL-on-FHIR spec. The one exception is Bulk `$export`, an async job that writes NDJSON files, simple enough to implement over the lake without a full server.

Bulk `$export` fits both directions. In: its output is NDJSON, one resourceType per file, exactly pluginlake's canonical ingestion format (point 8); it is the batch counterpart to the streaming push (streaming for real-time, `$export` for backfills and periodic full pulls, no conversion), which refines point 9 where `$export` was listed only as a batch option. `$export` is a server operation, so pulling it from ViscoSuite needs ViscoStore; the ViscoLink-only path uses streaming or direct NDJSON dumps. Out: if FHIR is ever served, `$export` is the most lakehouse-friendly operation (batch, async, file-oriented NDJSON, not per-resource OLTP search) and can be generated straight from gold FHIR tables, so bulk-out is cheaper than interactive search.

FHIR serving option matrix (all deferred until a real consumer exists):

| Need | Options | Notes |
|---|---|---|
| Full FHIR REST (interactive search, write, operational) | HAPI FHIR (OSS, JVM, Postgres); Firely Server / Vonk (.NET, commercial); Aidbox by Health Samurai (commercial, Postgres) | Aidbox leans toward analytics and is strong on SQL-on-FHIR; Health Samurai are core SQL-on-FHIR and ViewDefinition contributors |
| FHIR-shaped analytical or bulk views only | SQL-on-FHIR: Pathling, or the ViewDefinition spec implemented over the lake (Aidbox also supports this) | Most DuckLake-aligned; no operational CDR; transforms FHIR to tabular views |
| Bulk extract only | Generate `$export` NDJSON directly from gold FHIR tables | No server needed; simplest serve-out |

Choose by whether consumers need interactive FHIR search and write, or only tabular and bulk FHIR.

Conclusion: for the ingest-FHIR, serve-OMOP path no FHIR server is needed; if FHIR-out is ever needed it is a small, bounded, rebuildable projection over gold, deferred until a real consumer exists. Do not build FHIR search from scratch: Bulk `$export` matches pluginlake's NDJSON on the way in and is the cheapest FHIR surface on the way out; for a full FHIR API evaluate HAPI, Firely, or Aidbox, and for FHIR-shaped analytics prefer lake-native SQL-on-FHIR (Pathling or ViewDefinition).

## 12. ViscoLink-only versus ViscoLink plus ViscoStore

The two deployment shapes for the ViscoSuite side. This refines the two-copy assumption in point 5 and the source-of-truth note in point 8.

| Aspect | ViscoLink-only (lean) | ViscoLink + ViscoStore (full) |
|---|---|---|
| What runs | stateless integration engine only | integration engine plus a HAPI FHIR JPA CDR (Postgres-backed) |
| Data flow | event-driven streaming pass-through, no persist, straight to pluginlake | messages persisted into an operational FHIR store, then handed off |
| Silos | one copy on our side (pluginlake); no edge datastore | two datastores (ViscoStore CDR plus our lake) |
| Operational FHIR serving | none on the edge | full: FHIR search, Subscriptions, `$export`, MCP, tester UI |
| Durability and replay on the edge | none; pluginlake bronze (plus broker retention) is the first durable capture | ViscoStore is a durable edge SoR you can replay from |
| Deployment and ops overhead | minimal (one stateless service per site) | higher (extra WAR, Postgres, backups, scaling) |
| Source of truth | origin clinical apps; earliest durable copy is our bronze | origin apps plus ViscoStore as an edge SoR |

When to choose which:

- ViscoLink-only if the goal is ingest FHIR then serve OMOP analytics. This is the lean default. It fits the reality that Chipsoft does not provide usable direct FHIR and ViscoLink captures HL7v2 close to the source applications, so the integration engine is needed but the edge store is not.
- Add ViscoStore only if you need an operational FHIR CDR on the edge: live FHIR serving to clinical apps or other systems, FHIR search and subscriptions at the edge, or a durable edge replay point independent of pluginlake.

Conclusion: ViscoLink-only (streaming pass-through) is the lean default; ViscoStore is deferred until a concrete operational-FHIR-on-the-edge need appears. Dropping ViscoStore removes the second silo and most of the deployment overhead.

## 13. Streaming ingestion mechanics: receiver, broker, landing, reject

The stream is event-driven: a clinical event reaches ViscoLink, which emits FHIR per event (ViscoSuite confirmed this push model). pluginlake builds a receiver, not a trigger, with two decoupling buffers before the lake.

- Broker over webhook. Take events on a durable message broker, not a raw HTTP webhook. It bridges a per-event stream to a lakehouse that only accepts micro-batch commits (a DuckLake commit is a snapshot plus Parquet files; committing per event causes small-file and snapshot bloat).
- Two buffers, two decoupling points. The broker absorbs ViscoLink's push and decouples it from the writer; a consumer micro-batches events into files in the landing zone (raw dump); Dagster then picks those files up on its own cadence and commits one validated batch into bronze. This is the same file-drop decoupling as the batch or `$export`/folder-watch lane, so both lanes look identical to Dagster.
- Where a backlog sits. If the writer lags, events queue in the broker; if Dagster lags, the files queue in the landing zone. Once an event is written to the landing zone it is no longer in the broker (see the ack seam). Either way nothing is lost and Dagster catches up in larger batches, so high volume never makes Dagster go wild.
- The writer is cheap and horizontally scalable. Each event is an independent file write, no locks or transactions, so writers parallelize freely up to the broker's partition count and the broker only has to buffer a burst until they drain it. To stay cheap at high rates, micro-batch several events into one NDJSON file (pluginlake's canonical format) under date/hour/source prefixes rather than one tiny file per event: one-file-per-event multiplies per-object overhead (PUT/list request cost on object stores, inode and directory pressure on a filesystem) and leaves more small files for Dagster to compact at promotion.
- Landing zone is a raw dump, not a table: raw payloads as received, opaque and unvalidated, with a retention or cleanup policy once records are promoted or rejected. It is storage-agnostic via the StorageBackend abstraction: a local filesystem directory on a single-node Linux station, or object storage (`s3://…`) when clustered. Metadata (received_at, source, event_id, offset) rides in the path or a sidecar. The governed lakehouse begins at bronze, after the readability gate.
- Ack and dedup. ViscoLink's job ends when the broker accepts the event; the consumer commits its broker offset only after the file write is durable (fsync or object PUT ack; at-least-once). Carry an idempotency key (source event or message id) and dedup by idempotent file naming or `MERGE INTO` bronze at promotion.
- Open (point 6): whether the streaming lane persists a file raw dump at all, or Dagster micro-batches straight from the broker. Broker-only makes the broker both buffer and landing zone, and then a Dagster-lag backlog sits in the broker instead of the dump.

Malformed data is rejected, not late-bound:

- Late binding is about semantics, not structural validity. Not-technically-readable FHIR fails the structural contract and can never be salvaged, so it is rejected at the boundary and never enters bronze; readable-but-not-conformed data is admitted and deferred (bronze to silver to gold).
- Reject is not silent delete: NACK or reject-to-source (only the source can fix it), dead-letter to a rejects sink or DLQ, and count and log the reason. Rising rejections are the early signal that the source contract drifted (the Chipsoft-connector churn risk). This is the two-boundary split from point 6: ViscoLink rejects on FHIR conformance at its edge, pluginlake rejects on readability at its edge (defense in depth).

Conclusion: broker for durable buffering, a consumer micro-batches events into the landing-zone raw dump, Dagster validates and commits to bronze on a cadence (never per event); ack after the file write is durable, dedup by idempotency key, reject malformed data at the gate with source feedback and metrics.

## 14. Real-time analytics and serving: a separate future workstream

Scope: today only the edges can be OLTP or streaming, the ingestion layer (ViscoLink push, streaming receiver) on the way in and the gold serving layer (an optional FHIR-out projection) on the way out; everything in between is batch and OLAP (DuckLake, Dagster, OMOP queried through DSP). This section lays the foundation for what a fully OLTP and streaming flow through the platform would look like. That end-to-end real-time path is wanted but deferred to a separate workstream, not built in this phase.

Why it is a separate workstream and not a config change: the current stack is batch-centric by design, and two governance pieces in particular assume batch.

- Catalog: DuckLake is snapshot and commit based (batch), not a streaming sink.
- Lineage: Dagster's lineage is asset and materialization based (batch runs), not continuous stream topologies.

What a streaming analytics and serving layer would add or replace (the batch lake stays as-is for analytics):

- Streaming compute engine: a continuous stream processor (Flink, Spark Structured Streaming, RisingWave, Materialize, Arroyo) for event-time windows, watermarks, and incrementally maintained views, in place of Dagster plus Polars batch on that path.
- Real-time serving store: a real-time OLAP store for sub-second queries on fresh data (ClickHouse, Druid, Pinot), or an OLTP or FHIR serving store for point reads (Postgres, ViscoStore), in place of DuckLake for the served slice.
- Streaming-aware catalog, lineage and schema governance: keep the batch catalog and lineage for the lake, and add a schema registry for topic schemas and compatibility (Confluent Schema Registry, Apicurio) plus streaming lineage (OpenLineage from the stream processor, surfaced in DataHub or OpenMetadata), ideally federated into one catalog that models both tables and topics.
- Event-time and state semantics: watermarks, windowing, and exactly-once state stores, which the batch catalog and lineage do not model.

Streaming tool landscape (a starter menu, all deferred). Python is pluginlake's default, so Python-native options are flagged; but this is best-tool-for-the-job, and a non-Python tool is fine when clearly better. Leaving Python needs a clear, obvious motivation (for example, Flink's exactly-once stateful processing or ClickHouse's ingest and query performance, which have no Python-native equal):

A note on two things also called "streaming" but that are not the streaming plane: Polars has a streaming engine and DuckDB pipelines its execution, but that is out-of-core batch (processing larger-than-memory data in chunks on one machine), with no event-time, watermarks, or continuous incremental views. It belongs in the batch plane (it can make silver and gold promotion more memory-efficient) and does not turn Polars or DuckDB into a stream processor.

Stream processors (compute):

| Tool | Character | When |
|---|---|---|
| Apache Flink | the mature heavyweight; true event-time, windowing, exactly-once state; JVM, operationally heavy | serious, high-scale streaming where correctness and state matter |
| Spark Structured Streaming | micro-batch streaming on Spark; higher latency | already invested in Spark |
| RisingWave | streaming database, Postgres-wire, SQL materialized views; Rust | SQL-first streaming without Flink's ops burden |
| Materialize | streaming database, Postgres-wire, incremental view maintenance; strong consistency | real-time analytics expressed as SQL views |
| Arroyo | newer Rust, SQL stream processing; lightweight | a leaner Flink alternative |
| Bytewax (Python) | Python-native stateful stream processing, Rust core | staying in the Python stack |
| Pathway (Python) | Python streaming and batch framework, Rust engine; ML and LLM friendly | Python, unified batch and stream, analytics or ML |
| Quix Streams / Faust (Python) | Python stream-processing libraries on Kafka | lightweight Python consumers on Kafka |

Real-time serving stores (fast queries on fresh data):

| Tool | Character | When |
|---|---|---|
| ClickHouse | column-store, very fast analytics, high ingest; SQL | general real-time OLAP, dashboards, high write throughput |
| Apache Druid | real-time OLAP for event and time-series data; sub-second, high concurrency | time-series and event analytics at scale |
| Apache Pinot | ultra-low-latency, high-concurrency OLAP | user-facing, high-QPS analytics |
| StarRocks / Apache Doris | MPP real-time OLAP, MySQL-wire; StarRocks also queries the lakehouse | real-time plus direct lakehouse querying |
| TimescaleDB | Postgres extension for time-series; simpler, lower scale | modest scale, Postgres-native |
| Postgres or a FHIR server (ViscoStore, HAPI) | OLTP point reads, not analytics | operational point lookups or FHIR-shaped serving |

DuckDB Quack (new and experimental, from DuckDB Labs) is worth watching here: it is a client-server protocol over HTTP that gives DuckDB concurrent multi-user, multi-writer access, turning DuckLake into a shared analytical serving endpoint without a separate database. It is relevant to serving the lake to several concurrent users while staying in the DuckDB stack, but it is still OLAP query execution, not a real-time streaming engine and not an OLTP point-read store.

Streaming governance (schema and lineage):

| Tool | Character |
|---|---|
| Confluent Schema Registry | Avro, Protobuf, JSON Schema with compatibility enforcement; Kafka-centric |
| Apicurio Registry | open, multi-format schema registry |
| OpenLineage | open lineage standard with Flink and Spark integrations |
| Marquez | reference OpenLineage server |
| DataHub / OpenMetadata | catalogs that span batch tables and Kafka topics, so one catalog can cover both planes |

Transport note: the broker itself could be Kafka, Redpanda (Kafka-compatible, Rust, leaner ops), NATS, or Pulsar; this overlaps open point 4.

Why this is feasible as an additive step, not a rewrite: pluginlake is composable (decoupled, containerized components with framework-agnostic seams), so the migration is a per-component review, keep what is already streaming-ready and swap what is batch-bound. The broker and the framework-agnostic StorageBackend are the natural swap points.

| Batch component (now) | Role | Later, for the streaming plane |
|---|---|---|
| Broker (Kafka, NATS) | transport and buffer | reused as-is; already streaming-native and the source a stream processor reads |
| Raw dump plus bronze | durable capture and analytical copy | reused as-is; stays the durable copy feeding batch analytics |
| Dagster plus Polars | orchestration and batch compute | stream processor (Flink, RisingWave, Materialize, Arroyo) on that path |
| DuckLake | analytical store and catalog | real-time OLAP (ClickHouse, Druid, Pinot) for the served slice; batch lake unchanged |
| Dagster asset lineage | lineage | add streaming lineage (OpenLineage, surfaced in DataHub or OpenMetadata) |
| Implicit load-time schema | schema governance | add a schema registry (Confluent, Apicurio) |
| plugin-rosetta | domain transform | reusable as a library, or reimplemented as a streaming transform |

The real-time workstream attaches a stream processor and a serving store to the same broker rather than re-plumbing ingestion.

Conclusion: Real-time analytics and serving are deferred to a separate workstream, made feasible by pluginlake's composable, per-component substitution. The batch lake, catalog and lineage stay as they are for analytics; the streaming plane is additive (a stream processor, a real-time serving store, and streaming-native schema and lineage governance), fed from the same broker.

---

## Settled decisions (also stored as repository memories)

1. Single canonical ingestion format: FHIR R4 JSON NDJSON, one resourceType per file; other and output formats on demand, never ingested in parallel.
2. Medallion plus late binding: a raw landing zone (a raw dump, not a table) drops off exactly what arrived; the bronze gate validates technically-readable legal FHIR (bronze is the first governed table); FHIR-common-data-model conformance at silver; curated serving products at gold (OMOP plus terminology is the analytics product today). Gold is the curated serving tier, not OMOP-locked: pluginlake is standards-open, so gold can materialize whatever standard a consumer needs (OMOP, a curated FHIR mart, others later).
3. Real-time or streaming ingestion via a standing service outside Dagster that drops raw events into the landing zone; a broker buffers the streaming lane so Dagster promotes into bronze on a cadence or threshold, never per event; DuckLake is not a streaming sink.
4. ViscoLink-only (streaming pass-through) is the lean default; ViscoStore and any HAPI or Firely FHIR server are deferred until a concrete operational-FHIR need appears.
5. If a FHIR server is ever needed it is a small, bounded, rebuildable serving projection over curated gold, projected from the FHIR side (silver), never the system of record or ingestion sink.
6. Streaming uses a broker as the bridge from per-event push to the lakehouse's micro-batch commits: a consumer micro-batches events, Dagster promotes into bronze on a cadence (never per event); ack after the write is durable; dedup by idempotency key (idempotent file naming or MERGE into bronze at promotion). Whether the streaming lane also persists a separate raw dump is open (see open point 6).
7. Malformed data is rejected at the boundary (a structural contract violation, not a late-binding case); reject means reject-to-source plus dead-letter plus metrics, not a silent drop.
8. FHIR Bulk `$export` is the batch counterpart to the streaming push and outputs pluginlake's canonical NDJSON format, so it fits ingestion with no format conversion; it is also the cheapest, most lakehouse-friendly FHIR serve-out. Do not build the FHIR search framework from scratch.
9. Real-time analytics and serving are deferred to a separate workstream, made feasible by pluginlake's composable, per-component substitution; the batch lake, catalog (DuckLake) and lineage (Dagster) stay as-is for analytics, and the streaming plane is additive (a stream processor, a real-time serving store, and streaming-native schema and lineage governance), fed from the same broker.
10. The OLAP lake is never on the fast path: streaming velocity is absorbed by the broker and the raw dump (both OLAP-free), and only async batch promotion touches DuckLake; real-time serving (true OLTP) is a separate layer, never the lake.
11. Openness and optionality by design, so any standard, model, or tool can be swapped later without re-ingesting: adopt specific tools only when a concrete need justifies it, keep open standards as the interchange, defer interpretation through late binding, and route all standard-to-standard and code-system translation through rosetta (plugin-rosetta) as the mapping and ontology layer. The canonical open-standard data plus rosetta's mappings can always re-project into a new target model or output standard, which is what prevents lock-in.
12. Because pluginlake is a lakehouse, not a free-form data lake, this is a laddered transition from schema-on-read to schema-on-write, not an unconstrained mix: the landing zone stores raw (schema-on-read, opaque, as-arrived, kept for replay); bronze is the point where data has to be readable and picked up by our systems so it can be catalogued and governed (the entry into the governed lakehouse); silver is where we understand the content (semantic conformance) and can transform it into other formats and standards via rosetta. The freedom to store in the best physical format for processing (columnar Parquet and DuckLake for OLAP, NDJSON or a FHIR shape for interchange and FHIR-out) and to re-project into other formats is realized from silver onward, once content is understood, not freely at every layer.

## Open points to finalize

1. Deployment topology and where ViscoSuite physically sits (private in-cluster module versus separate integration cluster), now leaning to option A, the in-cluster module. See points 10 and 12.
2. Whether a FHIR-out consumer will ever exist, which decides if a bounded FHIR serving projection over gold is built, and which serving option to use (HAPI, Firely, Aidbox, or lake-native SQL-on-FHIR). See point 11.
3. Whether to adopt dlt for non-FHIR source extract-load, and how to avoid overlap with the existing loader and Dagster path.
4. The concrete broker choice (RabbitMQ, Kafka, NATS) and delivery guarantees for the streaming path. See point 13.
5. Closing the bronze validation gap in `fhir/loader.py` (resourceType and readability check, reject-to-source, dead-letter, and metrics, instead of a JSON-only parse that silently drops).
6. Streaming landing zone shape: broker-only buffering versus also persisting a raw dump for the streaming lane, plus the raw dump's retention or cleanup policy and the Dagster trigger cadence or threshold. See points 9 and 13.
7. The concrete streaming-plane stack for the future real-time workstream: stream processor (Flink, RisingWave, Materialize), real-time serving store (ClickHouse, Druid, Pinot, or an OLTP or FHIR store), and streaming schema registry plus lineage. See point 14.
