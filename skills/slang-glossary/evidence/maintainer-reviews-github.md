# Experts: Tess and Yong on GitHub, 2024-11-05 to 2026-11-05

Source: the GitHub REST API through `gh api`, read-only. We searched `repo:shader-slang/slang is:pr commenter:<login>` in two updated-date ranges, capped at 600 PRs per author, most recent first. The recent range is PRs updated on or after 2025-11-05; the older range is PRs updated between 2024-11-05 and 2025-11-04. For every PR we fetched inline review comments, top-level reviews with a body, and issue comments, then kept the two authors' own comments. A comment's range is its creation date, so older-dated comments on a recently updated PR count as older year; that is why 'PRs with comments' can exceed 'PRs searched' for a range. Another 44 comments older than 2024-11-05 are kept in the JSONL but excluded from every count. The run used 2175 API calls, 17 of them searches, against a budget of 3,000.

| Author | GitHub | Range | PRs searched | PRs with comments | Comments | Inline (root / reply) | Reviews | Issue comments | On own PRs | Median words |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Tess (Theresa Foley) | `tangent-vector` | recent | 146 | 115 | 1427 | 1221 (638 / 583) | 55 | 151 | 694 | 51 |
| Tess | `tangent-vector` | older | 49 | 54 | 366 | 279 (213 / 66) | 18 | 69 | 82 | 50.0 |
| Yong (Yong He) | `csyonghe` | recent | 418 | 218 | 895 | 711 (324 / 387) | 83 | 101 | 408 | 24 |
| Yong | `csyonghe` | older | 182 | 204 | 713 | 446 (318 / 128) | 68 | 199 | 113 | 17 |

Three caveats shape how to read the counts. First, 694 of Tess's recent comments and 408 of Yong's are on their own PRs; those are replies to reviewers and bots, and 232 of hers and 113 of his read as agent-written close-outs. Second, 45 of Tess's comments are Codex-drafted reviews posted on her behalf on PR 11210, with IDs such as C003 and FG002; she signed them, so they count as hers. Third, 334 of Tess's recent comments are on bot-authored PRs, where her tone is sharpest. Tess's recent reviews were 38 changes-requested and 10 approvals; Yong's were 59 comments, 10 approvals and 8 changes-requested.

Tess also authored 67 PRs in the window, whose descriptions follow the five-part template and include a Concepts and Vocabulary section; those definitions feed part (a).

Quotes are at most 25 words and were machine-checked as exact substrings of the stored comment; `[n]` is the comment index in `github-comments.jsonl`, and the dumps `tess-gh.txt`, `tess-gh-older.txt`, `yong-gh.txt`, `yong-gh-older.txt` carry the same numbers. Findings that come only from the older year are collected in part (d) and marked "older year" elsewhere.
## (a) Terminology

### Tess: terms she uses

Counts are mentions / comments / PRs over all 1,793 in-window comments, with older-year mentions in parentheses (regex over bodies, code blocks included).

| Term | Mentions / comments / PRs | How it is used |
| --- | ---: | --- |
| proper type | 54/21/6 (o 6) | The type of a proper value; interfaces are not, existential boxes are. |
| existential value / box | 107/36/7 (o 11) | A boxed value over a contract; `dyn IFoo`; "existential type" alone confuses. |
| witness | 135/67/15 (o 2) | The proof value for a conformance; found or solved, never written. |
| `this` parameter / receiver | 109/50/9 | The implicit parameter of a method; its mode is the effective mode. |
| parameter-passing mode | 97/54/9 (o 1) | in, out, inout, borrow, ref; computed once, read everywhere. |
| effective | 41/23/9 | The computed result after modifiers, context and policy are applied. |
| borrow | 29/17/7 (o 13) | The real concept behind `__constref`; `inout` is an exclusive mutable borrow. |
| layout / layout unit / LayoutResourceKind | 304/93/31 (o 30) | Size and alignment per unit; bytes, slots, registers. |
| bytes / byte-granularity | 142/70/13 (o 23) | The correct word for what legacy code calls "uniform". |
| uniform | 54/41/16 (o 1) | Used only in scare quotes or when the legacy name is unavoidable. |
| shadow (variable/temporary) | 66/37/2 (o 1) | The compiler-created copy of a uniform parameter under `-Gec`. |
| dialect | 55/29/11 (o 1) | HLSL-flavored and GLSL-flavored dialects of Slang; never "mode". |
| diagnose / diagnostic | 256/165/47 (o 19) | Report an error or warning; always diagnose the unknown. |
| semantic checking / checker | 172/116/37 (o 23) | The phase that owns validity and policy decisions. |
| lowering / lower-to-IR | 104/75/31 (o 22) | The mechanical translation of the checked AST; never "code generation". |
| legalize / legalization | 49/30/12 (o 11) | Upstream IR passes that rewrite target-illegal shapes. |
| front end / front-end | 47/38/22 (o 5) | The half that decides; the back end only reads the IR. |
| pass (IR pass) | 239/181/52 (o 51) | A standalone .h/.cpp pair with a verb in its name. |
| decl-ref | 65/34/14 (o 11) | A declaration reference with substitutions; never demoted to `Decl*`. |
| canonical | 26/17/8 (o 1) | The one representation downstream code reads as-is. |
| producer / consumer | 33/24/11 | The phase that builds a shape versus the phase that reads it. |
| contract | 138/110/31 (o 1) | What a declaration promises its caller; what a doc comment states. |
| policy | 84/64/33 (o 2) | A design decision that lives in exactly one place. |
| invariant | 88/65/26 (o 2) | What must hold; asserted, never tested-and-bailed. |
| predicate | 83/51/19 | A named Boolean helper replacing a compound condition. |
| early-out | 33/21/16 | A return, continue or break before the main path; asserted or justified. |
| bottleneck | 18/15/11 (o 4) | The single routine every duplicate of a check flows through. |
| documentation comment / doc comment | 67/46/22 (o 1) | A comment on a declaration, `///` or `//`, for the client. |
| implementation comment / implementer-facing | 31/24/17 | Strategy and rationale inside the body, for a future maintainer. |
| rationale | 63/55/35 (o 3) | The why that every change and comment must supply. |
| terminology / term of art / precedent | 74/58/24 (o 12) | Terms are defined before use and never coined when precedent exists. |
| imperative / declarative voice | 19/15/7 | Comments use declarative "we", never imperatives. |
| task at hand / problem statement | 18/15/7 | What an implementation comment sets up first. |
| code smell / smelly | 32/31/20 | A shape that signals a design or layering bug. |
| band-aid | 14/12/12 (o 1) | A fix at the symptom layer that leaves the root cause. |
| CYA | 8/8/6 | A "safe" guard that hides an impossible shape. |
| slop / agent-speak | 38/30/13 | Grammatical prose that conveys no architecture, strategy or rationale. |
| hack / hackery / kludge | 38/30/20 (o 2) | Ad hoc logic inside a general mechanism; tolerated only when labeled. |
| carve-out | 13/11/10 (o 1) | A special case exempted from a general rule; suspect by default. |
| ad hoc | 23/18/12 (o 2) | Case-by-case logic where a systematic rule belongs. |
| systematic | 24/16/12 (o 2) | Following a representation change through every consumer. |
| WAR / workaround | 9/9/7 (o 1) | Tolerated only with a filed bug and a reproducer. |
| dirty laundry | 6/6/6 (o 1) | History or process in a comment that readers do not need. |
| sweep under the rug | 7/7/7 (o 1) | Hiding a policy decision or an inconsistency. |
| Right Way / Just Work | 37/34/23 (o 11) | What a principled representation makes possible. |
| high-order bit / low-order nit | 6/5/5 | Her explicit ranking of feedback by importance. |
| agent / LLM / bot | 276/245/48 (o 7) | Agent-authored code is held to the human bar. |
| clarity review / self-review | 12/9/6 | The review criteria authors apply to themselves before posting. |

### Yong: terms he uses

Counts are over all 1,608 in-window comments; older-year mentions in parentheses.

| Term | Mentions / comments / PRs | How it is used |
| --- | ---: | --- |
| test | 292/180/92 (o 109) | A test must exercise the real path and run on all applicable targets. |
| diagnose / diagnostic | 131/96/35 (o 54) | Emit a user-facing error at the right phase; new diagnostics need tests. |
| witness | 92/56/16 (o 6) | The conformance proof; looked up by key, invoked at lowering. |
| pass (IR pass) | 118/94/55 (o 37) | Keep the pipeline small; put each rewrite in the pass that owns it. |
| lowering / lower-to-IR | 76/58/39 (o 19) | A dumb mechanical translation; never rediscovers high-level facts. |
| emit / emitter | 67/51/41 (o 24) | A printer of the IR; never a place for fixes. |
| legalize / legalization | 30/25/19 (o 14) | Where target-specific rewrites happen before emit. |
| specialization / specialize | 60/50/21 (o 6) | The word for generic application and the IR pass; not instantiation. |
| fold / const-fold | 65/39/17 (o 5) | Compile-time evaluation, and merging logic into one place. |
| fast path | 22/8/1 | Hard-coded handling that skips general resolution for builtins. |
| peephole | 8/8/2 | The pure simplifier; home of fold-level checks, no diagnostics. |
| DCE | 4/3/3 (o 2) | Dead-code elimination, trusted to clean leftovers. |
| dedicated IR opcode / kIROp | 17/15/14 (o 4) | A named instruction for anything passes must recognize. |
| IR instruction / inst | 96/68/52 (o 35) | Operands carry relations; decorations and name hints do not. |
| decl-ref | 32/25/10 | Always a DeclRef when a reference to a decl is meant. |
| facet | 8/5/3 | A conformance entry in inheritance info; extend it, do not invent declref kinds. |
| synthesi | 36/20/14 (o 12) | Compiler-created declarations; go through the requirement-synthesis path. |
| sub / sup | 7/7/3 (o 1) | The two sides of a constraint; the only sanctioned words. |
| existential value / box | 11/7/6 | An interface-typed value: RTTI header plus payload union. |
| type conformance / type id | 7/3/3 | Test-side registration for dynamic dispatch with runtime ids. |
| capability | 46/22/16 (o 17) | Atoms that imply one another; a true disjunction is unrepresentable. |
| backend | 41/27/19 (o 5) | Per-target code; shared code assumes no single target layout. |
| front end / front-end | 16/14/12 (o 7) | Where a fix usually belongs when lowering crashes. |
| follow-up / separate PR | 75/66/20 (o 7) | Explicit deferral of out-of-scope work. |
| redundant | 21/19/8 (o 3) | A check an earlier stage already guarantees; delete it. |
| guard | 21/19/13 (o 1) | A defensive check that kicks the can; replace with an assert. |
| assert | 23/22/13 (o 2) | Loud failure when an invariant breaks. |
| invariant | 13/13/6 | A property guaranteed by construction. |
| post-emit metadata | 7/5/3 | The one channel for user-queryable facts about emitted code. |
| mutex / race / thread-safe | 8/8/3 | Shared caches need a lock and a proof. |
| compile time (perf) | 15/13/11 (o 1) | Expensive work is done once and gated. |
| internal (visibility) | 16/16/10 (o 4) | Marks core-module helpers users must not call. |
| experimental | 13/11/8 (o 7) | Opt-in modules subject to change or removal. |
| deprecate | 4/4/4 | Mark now what a future version removes. |
| clean / cleaner | 35/35/29 (o 8) | His summary verdict on an implementation. |
| band-aid | 2/2/2 (o 1) | A symptom fix that is not a fix. |
| terminology / term of art / precedent | 18/16/9 (o 1) | Codebase words win over invented ones. |
| agent / LLM / bot | 67/57/38 (o 39) | Authors must vet and answer AI review comments. |
### Tess: corrections of words

Each row is one correction; `[n]` is the comment index in `github-comments.jsonl` and `tess-gh*.txt`. Rows marked `(reply)` come from her replies on her own PRs, where her agent reports an accepted rename.

#### Layout, bytes and offsets

| # | Correction | Quote (≤ 25 words) | PR | idx |
| --- | --- | --- | --- | --- |
| G1 | "uniform" (meaning bytes) → bytes, byte-granularity | "we should avoid ever using the word "uniform" to mean bytes" | 12306 | [1371] |
| G1 | same, in docs | "we have a very real problem in Slang that the concept of "uniform" is horribly overloaded" | 11135 | [1325] |
| G1 | same, as a type adjective | "I would prefer an adjective other than "uniform" be used here to describe the category of type being checked for." | 13445 | [2159] |
| G1 | `Uniform` as a synonym for bytes → `slang::ByteRange` | "Please also avoid `Uniform` as a synonym for bytes and use the public `slang::ByteRange`" | 11135 | [1358] |
| G2 | `slang-ir-uniform-usage.*` → `slang-ir-byte-granularity-usage.*` | "I would advocate for `slang-ir-byte-granularity-usage.*`." | 11135 | [1195] |
| G2 | `UniformUsageRange{byteOffset,byteSize}` → `ByteGranularityUsageRange{offset,size}` | "Why isn't the type `ByteGranularityUsageRange` with `offset` and `size` as the fields?" | 11135 | [1202] |
| G2 | "uniform field usage" → byte-granularity usage of binding ranges | "The name "uniform field usage" implies a level of generality that just isn't here." | 11135 | [1215] |
| G3 | "used/read/uniform" → "potentially used" | "Please rename the current “used/read/uniform” terminology accordingly" | 11135 | [1355] |
| G3 | "byte ranges are read" → "used" | ""how many byte ranges are read" should probably be "how many byte ranges are used"." | 11135 | [2395] |
| G4 | "loose uniform parameters" → no such concept; `$Globals` is a historical name | "There is no concept in Slang of "loose uniform parameters."" | 11135 | [1337] |
| G5 | "host" → "host application" or "application" | ""host" on its own means the host *machine*/device, and not the host application process" | 11135 | [1333] |
| G6 | "reflection offset" → offsets; "absolute" → cumulative | "The term "reflection offset" is meaningless. Just use "offsets" here." | 12715 | [1527] |
| G7 | "unit" vs "kind" (layout) → one notion | "seems to be mixing up the notions of "unit" and "kind," even though they mean the same thing here." | 12544 | [1702] |
| G7 | `kind/size/alignment` triple → `AtomicLayoutInfo` with a `unit` field | "I'd like to see the `kind`/`size`/`alignment` as stored above factored out into a distinct `AtomicLayoutInfo` type" | 12544 | [1706] |
| G8 | `setSecondUnit` → `addUsage` | "I'd just change them to call `addUsage` instead of `setSecondUnit`." | 12544 | [1712] |
| G8 | `ObjectLayoutInfo` for simple layouts → extend `SimpleLayoutInfo` | "`ObjectLayoutInfo` is for the layouts of "object" types like textures/buffers/etc." | 12544 | [1648] |
| G8 | `isContainer` (bool) → `SingleElementContainerPartKind` enum | "the new name of `isContainer` is very generic and doesn't strongly imply what behavior it is requesting" | 12544 | [1646] |
| G9 | size/alignment fundamental, stride derived | "size/alignment are fundamental, while stride is derived information" | 12022 | [1349] |
| G10 | `offsetIn(...)` vs `getCumulativeOffset` → one name for parallel ops | "Why does `AccessPathLink` have `offsetIn(...)` while `Cursor` and `AccessPath` have `getCumulativeOffset`?" | 12715 | [1541] |
| G10 | `navigateToField` → `navigateToFieldByName` / `...ByIndex` | "the `navigateToField` operations should be `navigateToFieldByName` and `navigateToFieldByIndex`, to avoid the ambiguity that arises for `navigateToField(0)`." | 12715 | [1542] |
| G11 | `isHLSLUniformDataType` → `isTypeAllowedForMutableGlobalVariable` (reply) | "Removed `isHLSLUniformDataType`. Shadows and ordinary mutable file/namespace statics now use `isTypeAllowedForMutableGlobalVariable`" | 13445 | [2181] |

#### Types, interfaces and existential boxes

| # | Correction | Quote (≤ 25 words) | PR | idx |
| --- | --- | --- | --- | --- |
| G12 | "value type" (`isExprOrValueType`) → "proper type" (`isExprOfProperType`) | "The term "value type" is being used here to mean what is traditionally called a *proper type*" | 12585 | [1409] |
| G12 | void-excluded case → "non-void proper type" | "I think we need the concept to be "non-void proper type" or "non-unit proper type"" | 12585 | [1409] |
| G13 | "existential type" → "existential box type" | "The term "existential type" leaves many people confused, if they don't have the PLT background to understand what that phrase implies." | 13885 | [2376] |
| G13 | "interface-typed values" → existential-box type, `dyn ITransform` | "the latter is the old and imprecise/incorrect term we had used for the former." | 13885 | [2432] |
| G13 | `IV` (interface) vs `dyn IV` (box) are not interchangeable | "We just need to work to be systematically correct in how we use interface types like `IV` vs. existential types like `dyn IV`." | 12555 | [1404] |
| G13 | "specializing with an existential type" → specializing with the unboxed type | "Instead we are specializing with a type that resulted from *unboxing a value of existential type*" | 12555 | [1406] |
| G14 | "single interface" → "contract" (interface or conjunction) | "I'm not sure if we should emphasize "single interface" so heavily, since an existential box makes sense over any "contract" (interface or conjunction of interfaces)" | 13885 | [2387] |
| G14 | interface vs interface *declaration* | "we should aspire to be precise about when/where we are talking about interfaces, vs. interface *declarations*" | 13885 | [2433] |
| G15 | "bare" (adjective) → avoid | "documentation, comments, etc. for the Slang project should avoid using the term "bare" as an adjective." | 13885 | [2435] |
| G16 | subtype / conformance / refinement are distinct relations | "then we have a contract *refinement* relationship: "`left` refines `right`"" | 13885 | [2392] |
| G16 | `SubtypeWitness` is misnamed (noted) | "a new subclass of `SubtypeWitness` (which is misleadingly named, but that's not our current problem...)" | 12555 | [1856] |
| G17 | "metadata" (for a compatibility witness) → compatibility-hack conformance witness | "This class is a necessary compatibility hack, and should not be seen as a precedent to excuse further unfounded conformance relationships." | 13885 | [2388] |
| G18 | "dynamic type" of an expression → "instance of a type" (reply) | "I would prefer that we not go down the road of having a notion of the "dynamic type" of an expression at runtime." | 12209 | [2084] |
| G19 | `isTypeDifferentiable` → `isTypeActuallyDifferentiable` over `doesTypeConformToADifferentiabilityInterface` | "Something like `isTypeActuallyDifferentiable(ty)` would check for `no_diff` first, and then delegate to something like `doesTypeConformToADifferentiabilityInterface(ty)`" | 13885 | [2390] |
| G20 | `isEqualityConstraint` bool → subclasses of `ConstraintDecl` | "make equality constraints be their own class of constraint and not keep using the `isEqualityConstraint` field as a type discriminator tag." | 12690 | [1661] |
| G21 | "resource" is undefined for `RayQuery`, `SamplerState` | "A `RayQuery` isn't a "resource" in the same way that a `Texture2D` or a `StructuredBuffer<float>` is, certainly" | 8754 | [1085] |
| G21 | "resource handle" → keep `isResourceType` | "Injecting the word "handle" into the name is actually making things more confusion rather than less" | 13116 | [1932] |
| G22 | `IRPtrType` → `IRPtrTypeBase` when any pointer is meant | "The code in this case really only cares about the type of the instruction being "a pointer" in the general sense" | 8754 | [1079] |
| G23 | `uint8_t`-style names → `UInt8` | "Slang's built-in integer types should follow the same `UpperCamelCase` naming convention we apply to other types" | 8960 | [1117] |
| G24 | "keywords" → "syntax" | "As a minor point, these are about *syntax* and not necessarily "keywords." (Slang doesn't really have keywords, in practice)" | 12568 | [1502] |
| G25 | `isMetaOp` / `isTypeOnlyInst` → `doesInstOnlyDependOnOperandTypesAndNotValues` | "the name `isTypeOnlyInst` is too brief to actually be specific" | 13116 | [1933] |

#### Parameters, receivers and passing modes

| # | Correction | Quote (≤ 25 words) | PR | idx |
| --- | --- | --- | --- | --- |
| G26 | "const ref", `ConstRef` → (immutable) borrow, `BorrowInParamType` | "the whole "const ref" terminology is inaccurate and never should have been introduced to the codebase in that form" | 13401 | [2483] |
| G26 | `__constref` → legacy alias for `__borrow` / `borrow` | "`__constref` is the legacy deprecated mode and should only be understood as a legacy alias for `__borrow`/`borrow`." | 12575 | [1486] |
| G26 | pass name → `transformByValueParamsToBorrows` | "this is a good chance to give if a more accurate name like `transformByValueParamsToBorrows` or something like that." | 13401 | [2485] |
| G27 | `const` (ref access) → `readonly`; `const` is a legacy alias | "The name `const` is incorrect, since it implies the data is constant" | 13406 | [2104] |
| G27 | "constant" → "read-only" (about access) | "we are using the term "read-only" instead of "constant" (as implied by `const`)" | 12575 | [1453] |
| G27 | printed mode → `ref readonly` / `readonly ref`; `writeonly ref` | "This should be `ref readonly` or `readonly ref`." | 13406 | [2102] |
| G27 | `__ref_readonly` in diagnostics → `ref readonly` | "In things like diagnostics these should print as `ref readonly` and `ref writeonly`." | 12575 | [1452] |
| G28 | `__ref` (internal uses) → `inout` | "a lot of the cases that are using `__ref` probably should actually just use `inout`" | 12575 | [1465] |
| G29 | `inout`/`out` "copy" → false; exclusive mutable borrow | "the `inout` and `out` modifiers do not indicate copying. We need to stop spreading lies in our own comments." | 11709 | [2472] |
| G29 | "copied in and copied back out" → "exclusive mutable borrow" | "This is not necessarily true for `inout` parameters, and framing it that way is dangerously misleading." | 11709 | [2467] |
| G30 | `groupshared` (parameter) → "by-reference parameter" in the group-shared address space | "A by-reference parameter is a category that is already defined cleanly and clearly." | 11709 | [2474] |
| G30 | "its `groupshared` memory" → implies ownership | "it implies that a function owns certain groupshared memory" | 11709 | [2468] |
| G31 | `isRefParamPassingMode` → `isByReferenceParamPassingMode` | "The name `isRefParamPassingMode` implies that it checks for exactly the single `ParamPassingMode::Ref`" | 13406 | [2105] |
| G32 | `getEntryPointParamDirections` → `checkEntryPointParamPassingMode` | "rename that routine to something more meaningful like `checkEntryPointParamPassingMode`." | 13406 | [2363] |
| G32 | isInput/isOutput derivation → `convertParamPassingModeToEntryPointParamDirections` | "it can even just be a helper `convertParamPassingModeToEntryPointParamDirections`, since that's the operation being done." | 13406 | [2348] |
| G33 | "mode ...ReadsArgument" → parameter; a mode grants permission | "It is more that the mode gives code within a function body permission to read from the parameter." | 13406 | [2339] |
| G34 | "location" → "memory location" or "abstract storage location" | "Just using "location" on its own not only fails to distinguish which of the two cases we mean in context" | 13406 | [2309] |
| G35 | read-only parameters are not "l values" | "I don't think we should be calling read-only parameters "l values" for our purposes for now..." | 12575 | [1467] |
| G36 | "wrap a pointer-like type" → act as a wrapper pointer-like type | "It is factually incorrect to state that some of these modes "wrap a pointer-like type."" | 12575 | [1483] |
| G37 | `getX` (inferred mode) → `getEffectiveThisParamPassingMode` | "I would prefer that this predicate be named `getEffectiveThisParamPassingMode` (or `getEffectiveThisParamMode`)" | 13213 | [2042] |
| G37 | `getThisParamInfo` asserts; `findThisParamInfo` returns optional | "An accessor `findThisParamInfo(DeclRef)` returns a `std::optional<ParamInfo>`." | 13213 | [2054] |
| G37 | `ensureFooIsAttached` → `checkAndAttachFoo` when invoked once | "This routine shouldn't have to be idempotent (an `ensureFooIsAttached` instead of `checkAndAttachFoo`), since it should only get invoked once on any given declaration." | 13213 | [2059] |
| G38 | "context declaration" → no such term | "there really isn't precedent for "context declaration" being an established/meaningful term in the codebase" | 13232 | [2065] |
| G39 | "value-type methods", "member function" → methods declared on a value type | "Slang is not C++! We should not default to C++ terminology just from inertia!" | 13506 | [2215] |
| G40 | "transparent receiver container" → invented | "What in the world is a "transparent receiver container"? Stop making up terminology that doesn't have precedent." | 13506 | [2230] |
| G41 | `ReceiverParam` for mode specifiers; `ThisExpr` for the breadcrumb (reply) | "The implicit-expression breadcrumb is `ThisExpr`, with `thisExprScope` and `getThisExprScope`, because it also covers constructor-local `this`." | 13615 | [2324] |
| G42 | Boolean field as imperative verb → proposition `shouldForwardAddressesOfEntryPointUniformParams` | "give it a name that works as a proposition (or a predicate, but that doesn't apply in this case)." | 13401 | [2482] |
| G43 | `RefParamType<T,A>` → distinct `RefReadOnlyParamType<T>` etc.; one `RefReadOnlyModifier` | "why not parse a single keyword that turns into a single modifier (e.g., `RefReadOnlyModifier`)?" | 13406 | [2347] |
| G44 | `QualType` → eventually `ExprInfo` | ""the thing that is currently called `QualType` but that should eventually just be called `ExprInfo`"" | 13406 | [2338] |

#### Shadows, dialects and front-end terms

| # | Correction | Quote (≤ 25 words) | PR | idx |
| --- | --- | --- | --- | --- |
| G45 | `compatibilityVar` → shadow temporary; class name must say "temporary shadow copy" | "The existing class name leaves out the most important point about what such a declaration represents." | 13445 | [2127] |
| G45 | "source global", "source reference", "source lookup" → drop "source" | "There is no such thing as a "source global" in Slang." | 13445 | [2167] |
| G45 | "source field access" → no such term | "Stop making up terminology without precedent and without any meaningful definition to put forward." | 13445 | [2160] |
| G46 | `hasMutableStorage` → `shouldBeImmutableAlias` (polarity) | "The `hasMutableStorage` flag seems like it is defined the wrong way around. It seems more like `shouldBeImmutableAlias`, or something like that." | 13445 | [2166] |
| G47 | "legacy `ConstantBuffer`" → "legacy `cbuffer` declaration"; "bare data parameter" → global-scope shader parameter | "A "legacy `ConstantBuffer`" is somewhat illogical/inconsistent." | 13445 | [2125] |
| G48 | "eligibility" → undefined | ""Eligibility" of what?" | 13445 | [2179] |
| G49 | `isD3DTarget` → `isHLSLBasedTarget` | "We should have something like `isHLSLBasedTarget` or whatever is appropriate to check whether the target *is* HLSL" | 13445 | [2162] |
| G50 | option → `EnableExtendedHLSLBackwardsCompatibility` | "`EnableExtendedHLSLBackwardsCompatibility` would be a more accurate name for this." | 13445 | [2118] |
| G51 | "HLSL mode" → "HLSL dialect" / "HLSL-flavored dialect" | "we should not refer to it as "HLSL mode" in user-facing documentation." | 13506 | [2222] |
| G51 | file → `a1-06-hlsl-dialect.md` | "lets name this `a1-06-hlsl-dialect.md`, and drop "flavored" from the file name." | 13506 | [2262] |
| G51 | "supports GLSL" → "GLSL-flavored dialect" | "(there is a reason I keep on talking about Slang having a "GLSL-flavored dialect" and avoid saying that Slang "supports GLSL")" | 13958 | [2404] |
| G52 | "allow" GLSL → "is": one dialect per translation unit | "I'd still claim that "is" is more appropriate than "allow" here" | 12836 | [1862] |
| G52 | `CompilerOptionName::AllowGLSL` → `DEPRECATED_LegacyAllowGLSL_DO_NOT_USE` | "rename `CompilerOptionName::AllowGLSL` to something suitably ugly like `DEPRECATED_LegacyAllowGLSL_DO_NOT_USE`" | 12836 | [1863] |
| G53 | `#lang` → `#language` | "I would argue for `#language`, to favor explicit clarity over aggressive concision." | 12836 | [1900] |
| G54 | "mutable per-invocation variable" → storage-neutral "mutable global variable" (reply) | "calling every diagnosed variable “per-invocation” would misdescribe group-shared storage." | 13116 | [2234] |
| G55 | `isGlobalDecl` → `isEffectivelyGlobal` | "I'm wondering that should be an `isEffectivelyGlobal` predicate, to be correct" | 13116 | [1924] |
| G56 | "program storage" → "storage" | "(just "storage," not "program storage," a made-up term that doesn't particularly add any value, AFAICT)" | 13872 | [2462] |
| G56 | "pointer `IRParam`" → "pointer-typed `IRParam`" | ""or pointer `IRParam`" should be "or pointer-typed `IRParam`"." | 13872 | [2461] |
| G57 | GLSL-module predicate → `hasGLSLSourceLanguageAttribute(ModuleDecl*)` | "Let's make this something like `hasGLSLSourceLanguageAttribute(ModuleDecl*)` so that it is accurate to what we are actually trying to test." | 13112 | [1911] |
| G58 | "refactor" vs "semantic change" | "This is a semantic change and not just a refactor." | 13112 | [1910] |
| G59 | "code generation" → AST-to-IR lowering | "the message is incorrect in using the term code generation" | 12575 | [1470] |
| G60 | `W00117` → "the deprecation warning" (reply) | "The two internal comments now refer to “the deprecation warning” rather than inventing a `W00117` spelling." | 12836 | [1805] |

#### Constraint solver vocabulary (PR 11210)

| # | Correction | Quote (≤ 25 words) | PR | idx |
| --- | --- | --- | --- | --- |
| G61 | "parameter value" → "argument value" | "Also, "parameter value" is 100% a mis-use of terminology here. I believe this wants to refer to the argument value (corresponding to some parameter)." | 11210 | [1235] |
| G62 | "constraints inferred" → the solver inferred; constraints constrain | "The constraints didn't infer anything." | 11210 | [1235] |
| G63 | "default expression" → "default-value expression" | "There is no such thing as a "default expression". Stop." | 11210 | [1245] |
| G63 | "default" → "default *argument*"; `getGenericParamDefaultArgVal` | "Write things precisely and you'll get the right answer. Also, now change the name of the function to `getGenericParamDefaultArgVal`." | 11210 | [1241] |
| G64 | "slot", "placeholder", "solver answer" → define before use | "Terminology should be defined before it is used." | 11210 | [1233] |
| G64 | "identity argument" → bad invented name | "What is an "identity argument"? That's not a pre-existing term of art inside the Slang codebase" | 11210 | [1234] |
| G64 | a default "runs" → "can or cannot be evaluated" | "a default type expression does not "run"; it can or cannot be evaluated/reduced yet because its dependencies are or are not resolved" | 11210 | [1261] |
| G65 | `SolvedArgInfo` → `GenericApplicationSlotInfo` | "Why is a type that represents additional info about a "generic-application slot" called `SolvedArgInfo`?" | 11210 | [1239] |
| G65 | `SolvedArgState` vs "trustworthiness" comment → one concept | "The type name and the comment above it are mutually inconsistent" | 11210 | [1230] |
| G66 | `Solved` / `Done` → `MadeProgress` / `NoProgress` | "The `Solved` case name is misleading: `Done` also means the constraint is solved, while `Solved` specifically means "made progress by changing the argument list."" | 11210 | [1272] |
| G67 | `doesParamHasDefault()` → `declaresDefaultGenericArgument()` | "The helper name `doesParamHasDefault()` is grammatically wrong, and it also hides the actual input contract" | 11210 | [1274] |
| G68 | `collectConstraints()` → setup/prepare name | "`collectConstraints()` does more than collect constraints: it also initializes the argument arrays that those constraints will later mutate." | 11210 | [1273] |
| G69 | `areTypesCompatibile()` → procedure-style name | "`areTypesCompatible()` reads like a pure, symmetric predicate. The implementation is neither" | 11210 | [1294] |
| G70 | `maybeCloneThisTypeWitness()` → it creates, not clones | "The function name and body comment say "clone" or "copy," but the body does not clone the input instruction." | 11210 | [1287] |
| G71 | "(incomplete) substitution" → `providedOrdinaryArgs` | "That term is misleading here because the object is not storing a `SubstitutionSet` or witness arguments" | 11210 | [1286] |
| G72 | stale `constraints` → `discoveredConstraints` | "This comment still says the context has a `constraints` list, but the field is now `discoveredConstraints`." | 11210 | [1258] |
| G73 | "Helper function to..." → say what it computes | "A comment that starts with "Helper function to..." tells us what role the function plays in the implementation, not what the function computes or returns" | 11210 | [1263] |
| G74 | `bool` + `outWitness` → return `TypeCoercionWitness*` | "You didn't find a `bool`; you found a witness." | 11210 | [1227] |

#### Naming conventions and grammar

| # | Correction | Quote (≤ 25 words) | PR | idx |
| --- | --- | --- | --- | --- |
| G75 | `consume*` / `parse*` (conditional) → `tryRead*` | "I would personally recommend that all of these operations be named `tryRead*()` where the `*` part is a noun phrase" | 9365 | [1129] |
| G76 | `UserId`, `defaultMdFileName` → `UserID`, `defaultMDFileName` | "acronyms/initialisms should always appear either entirely in upper case, or entirely in lower case (e.g., `UserID` instead of `UserId`)" | 10554 | [1159] |
| G77 | `_record_range` → `_record_range_if_nonempty`; "record" → "collect" | "I think "collect" is a better term overall because it is more obviously a verb whereas "record" could be a verb or a noun" | 11135 | [1202] |
| G78 | `_walkUses()` → name the action per use | "I can already guarantee you that it does more than "walk uses"" | 11135 | [1203] |
| G79 | `get...` that can fail → `find...` returning `std::optional` | "`get...` functions should be accessors that cannot fail (on input that is well-formed), while a `find...` function should be used for the failable case." | 12585 | [1421] |
| G79 | `_find*` that must succeed → `_get*` | "my main problem with this function is merely the fact that it is framed as a `_find*` instead of a `_get*`" | 11135 | [1200] |
| G80 | `get` on real work → `calc` / `compute` | "an accessor-like function that involves "non-trivial" computation should use `calc` or `compute` or similar for its verb, and not `get`" | 12715 | [1536] |
| G81 | "diagnose X" when conditional → "maybe diagnose X" / "diagnose X, if needed" | "This should either be "maybe diagnose modifier validity" or "diagnose modifier validity, if needed"" | 12596 | [1548] |
| G81 | `emitMemoryQualifierKeyword` → `maybeEmitMemoryQualifier` / `emitMemoryQualifierIfNeeded` | "it should be named as either `maybeEmitMemoryQualifier` or `emitMemoryQualifierIfNeeded`." | 12843 | [1695] |
| G81 | optional-returning query → `maybeInferDerivativeGroupMode` | "so that this query is more like `maybeInferDerivativeGroupMode`. That way it would be future-proof" | 13371 | [2093] |
| G82 | dictionary variable → `mapFooToBar` | "I would often name a variable like this `mapFooToBar`, where `Foo` and `Bar` represent the semantic role of the key and value, respectively." | 13539 | [2290] |
| G83 | noun-only pass name → verb: `eliminateUndefinedOpaqueHandles` | "Pick a verb and use it in the names..." | 14081 | [2444] |
| G83 | "eliminate uses" → must cover the handle too | "The name of the procedure would imply that it leaves the undefined handle around and just eliminates uses" | 14081 | [2456] |
| G83 | SPIR-V-specific predicate without SPIR-V in its name | "If the predicate has semantics deeply tied to SPIR-V, why isn't that encoded in its name in any way?" | 14081 | [2458] |
| G84 | "check" (result type) → disposition / verdict | "Referring to this type as a "check" seems semantically incorrect." | 12596 | [1517] |
| G84 | "target" (of a modifier) → "subject" | "refer to the construct being modified as the *subject* rather than the *target*." | 12596 | [1546] |
| G84 | → `queryModifierValidityOnSyntax` | "Let's call this `queryModifierValidityOnSyntax`, to be clear that this covers the case of a syntax node." | 12596 | [1512] |
| G85 | singular predicate → plural `areMemoryQualifiersAllowedOnParamType` | "The actual predicate is whether memory qualifiers (plural) are allowed on parameters of that type." | 12843 | [1693] |
| G86 | "throws type" → "`throws` clause" | "Refer to it as a "`throws` clause":" | 12876 | [1697] |
| G87 | `isEffectfulStatementForm` → `isExprSyntacticFormAppropriateForStmtLikeContext` | "the erroneously-named `isEffectfulStatementForm`" | 12585 | [1432] |
| G87 | "genuine call" → "call expression" vs "invoke expression" | "we should stick with "call expression" here and just drop the notion of "genuine"." | 12585 | [1427] |
| G88 | array "selection" → index into, get elements, subscript | "We index into an array. We get elements from it. We sometimes subscript it... we don't select from it." | 13539 | [2303] |
| G88 | `resourceSource` → `representativeSource` | "(not sure why its `resourceSource` instead of `representativeSource`...)" | 13539 | [2300] |
| G89 | `defaultArgsDeclRef` → `funcDeclRefForDefaultArgs` | "The name `defaultArgsDeclRef` implies "a decl-ref to the default args" whereas we actually mean "the decl-ref to use for determining default args"" | 12701 | [2308] |
| G90 | `declForMemoryQualifier` (variable) | "this variable name makes it sound like this is a declaration of a memory qualifier, whereas you really mean something more like `declForMemoryQualifier`" | 13445 | [2205] |
| G91 | `operator=` → never an operator; "actual operators" | "The actual distinction has nothing to do with lookup behavior" | 12781 | [1681] |
| G92 | `_handleSourceLanguageDirective` → `_tryApplySourceLanguageDirective` (reply) | "the helper is now `_tryApplySourceLanguageDirective`, and its documentation describes the boolean agreement/acceptance contract." | 12836 | [1774] |
| G93 | `add` vs `addRequirement` → one overloaded `add` (reply) | "This removes the misleading add/addRequirement naming distinction." | 12835 | [1744] |
| G94 | "moves" → "copies" (reply) | "Changed the declaration contract from “moves” to “copies” in 6fa3f4e80 so it matches the assignment followed by clearing the frontier." | 12830 | [1637] |
| G95 | rejection states uniformly `...Failed` (reply) | "Every rejected terminal state now has a `...Failed` name, including `TypeFailed`, `ConstraintFailed`, and `VisibilityFailed`." | 13506 | [2244] |
| G96 | `v.xxxx` → `float4(v.x)` | "Always prefer `float4(v.x)` over `v.xxxx’." | 11135 | [1220] |
| G97 | hard-coded `3` slice → `getFileNameWithoutExt` | "I really don't see why the `.md` is being removed with a hard-coded substring slicing operation, rather than the `getFileNameWithoutExt` operation" | 10554 | [1155] |
| G98 | executable → `slang-demangle` | "changed to something like `slang-demangle` or similar. Let's call it what it is" | 9365 | [1135] |
| G99 | "tie-breaker" (internal) → "legacy compatibility fallback" (reply) | "Internal helper, local, and comments now call the mechanism the legacy compatibility fallback. The diagnostic keeps tie-breaker because that is the user-facing description" | 12830 | [1615] |
| G100 | directory → `slang-embedded-standard-modules`; "monolithic" vs "separate" | "Rename the directory that contains this file to `slang-embedded-standard-modules`" | 14001 | [2464] |

#### Comment prose and diagnostic text

| # | Correction | Quote (≤ 25 words) | PR | idx |
| --- | --- | --- | --- | --- |
| G101 | imperative openers → declarative "we" | "Using imperative voice ("cache the desired `this`-passing mode...") instead of the project-preferred declarative voice with authorial "we"" | 13213 | [2047] |
| G101 | "Sort ...", "Handle ..." → declarative | "Why the imperative voice again with "Sort ..."? This is explicitly against the clarity guidance I've given, time and again." | 13506 | [2266] |
| G101 | "Keep the ..." → "We ..." | "Please prefer declarative statements with the authorial "we," as a way to express clear design intent." | 12136 | [1672] |
| G102 | paragraph-initial "This" → name the subject | ""This" at the start of a paragraph is fairly ambiguous." | 12136 | [1671] |
| G103 | personified values → a subject that acts | "Please avoid personifying objects/values like this, unless there is good reason." | 13445 | [2170] |
| G103 | "The temporary supports..." → "Shadow temporaries are used to support..." | "Say something like "Shadow temporaries are used to support legacy HLSL code that ..."." | 13445 | [2170] |
| G104 | "authored" in a comment → drop | "What in the world is the word "authored" doing here?" | 12596 | [1515] |
| G104 | "tiny", "uniform and null-safe" → no marketing | "Don't brag about nothing in your comments; it makes you look like an amateur." | 12568 | [1497] |
| G105 | "final design" / "currently the ..." → present tense | "Stop making reference to current-vs-future-vs-final language design choices and just talk in the present tense" | 12568 | [1493] |
| G105 | "(currently the ...)" aside → remove | "If you just eliminate the parenthetical aside, the comment would be accurate in perpetuity" | 12568 | [1505] |
| G106 | "the type axis" → plain description | "What in the world does "the type axis" mean in this documentation comment?" | 12596 | [1547] |
| G107 | "Shaders do not recurse" → stated precondition | ""Shaders do not recurse" - a deeply unfounded assumption to state with such certainty." | 14081 | [2455] |
| G108 | comment openers → "Requires ...", "Gives ...", "Returns null when ..." | "This sentence should start with "Requires ..." and similarly the next sentence should start with "Gives ..."" | 13116 | [2135] |
| G109 | plain `decl` in prose → backticked | "Use markdown backtick notation to clarify when a comment like this is referring to an entity in the code" | 13445 | [2164] |
| G110 | "allowed on the fragment stage" → "in" | "I think these uses of "on" should be "in."" | 12209 | [2082] |
| G111 | "exception", "caught" → error; "throwing" → raising | "Another use of "exception" that should be "error"." | 12209 | [2077] |
| G112 | `defer` tied to a statement → a runtime scope | "refers to deferred statements as being associated with a *scope* rather than with an enclosing *statement*." | 12209 | [2075] |
| G113 | "unexpected results" → "undefined behavior"; "the same" → "overlapping" | "We can realistically go from "unexpected results" to "undefined behavior" here, because that's what we're talking about..." | 13406 | [2372] |
| G114 | "every path reaches a return" → no path reaches the end of the body | "I think the restriction might be more rock-solid if phrased the other way around:" | 13460 | [2202] |
| G115 | diagnostic "a type or namespace" → name what the expression names | "Just having a general "a type or namespace" is both unhelpful and inaccurate." | 12585 | [1450] |
| G115 | diagnostic `TypeNameUsedAsExpressionStatement` → accurate name | "The diagnostic name `TypeNameUsedAsExpressionStatement` seems to be clearly inaccurate here." | 12585 | [1415] |
| G115 | E00120 → `source-language-directive-overrides-selected-language` (reply) | "E00120 is now named source-language-directive-overrides-selected-language and receives the selection provenance" | 12836 | [1748] |
| G116 | cast-to-void suggestion → "bind with `let`" | "We should not encourage the cast-to-void idiom." | 12585 | [1449] |
| G117 | semantic name vs semantic index; `SV_` system-value semantics | "split into a *semantic name* (which never ends in an ASCII digit) followed by a suffix of zero or more ASCII digits" | 12885 | [1840] |
| G118 | "A non-combined resource stays in one IR value." → "By default we allow ... because ..." | ""A non-combined resource stays in one IR value." - this is horrible slop." | 13116 | [2274] |
| G119 | "not recommended" → "compatibility behavior" of the HLSL dialect | "this is not just a not-recommended conversion, but one that is *only* included as a compatibility feature in the HLSL dialect." | 13113 | [1905] |
| G120 | `[nonmutating]` doc → `this` has the `in` parameter-passing mode | "A `[nonmutating]` attribute, which indicates that the `this` parameter of a declaration should have the `in` parameter-passing mode." | 13506 | [2226] |

### Yong: corrections of words

Yong's corrections are shorter and usually name the replacement directly.

| # | Correction | Quote (≤ 25 words) | PR | idx |
| --- | --- | --- | --- | --- |
| Y-C1 | "workgroup" → ThreadGroup; scopes are ThreadGroup, Wave, Thread | "The slang terminology for "workgroup" is actually ThreadGroup." | 10076 | [253] |
| Y-C2 | "instantiated" → "specialized" | "I believe we use the word "specialized" more than "instantiated"." | 10165 | [297] |
| Y-C2 | same, as doc policy | "specialization is what is being used in the codebase and in existing docs" | 10165 | [302] |
| Y-C3 | generic argument "type" → "proper type"; an interface is not one | "An `interface` by itself isn't allowed as specialization argument" | 10165 | [299] |
| Y-C4 | "struct extensions" → "extensions" / "generic extensions" | "`extensions` are not restricted to struct types. I would just call it extensions." | 10165 | [296] |
| Y-C5 | "Parameterization is allowed for" → a generic parameter can be a type or value | ""Parameterization is allowed for" this is confusing." | 10165 | [295] |
| Y-C6 | evaluation classes → "compile-time constant" and "link-time constant" | "i would call this compile-time constant and link-time constant, as in our existing user-guide documentation." | 10455 | [378] |
| Y-C6 | "specialization constant" used before definition | "term "specialization constant" is not defined at this point in the doc yet." | 10455 | [379] |
| Y-C7 | `constexpr` (docs) → `static const` | "The user should always use `static const` to mean "compiler time evaluation"." | 10455 | [376] |
| Y-C8 | `enum class` → `enum` (canonical) | "The canonical syntax is just `enum XXX`. `enum class` is another C++ compatibilty thing that shouldn't belong to the core language spec." | 11044 | [558] |
| Y-C9 | "storage class" → "address space" | "I am not sure why we need both the address space and storage class concept. We should only need address space?" | 10657 | [465] |
| Y-C10 | "endpoint" → "sub/sup type of the constraint" | ""endpoint" isn't an established terminology, should just say "sub/sup type of the constraint". Revise other mentions of "endpoint" as well." | 11368 | [689] |
| Y-C11 | `subtree` → `InstAndChildren` | "invent new terminology `subtree` here. Should be `doesInstAndChildrenUseBindlessResourceHeap()`" | 11436 | [805] |
| Y-C12 | "placeholder" → a real instruction not yet lowered | "The `IncrementCoverageCounter` instruction shouldn't be referred as placeholder. They have real semantic meaning, just not yet lowered to actual executable code." | 10886 | [528] |
| Y-C13 | `Decl*` getter → `...DeclRef` returning a `DeclRef` | "should be named getPackCountConstraintTargetDeclRef. Always use DeclRef if you mean a reference to a decl." | 11571 | [814] |
| Y-C14 | `Anchor` → descriptive name with examples | "What is `Anchor`? Should use a more descriptive name with proper comment (use concrete examples) to explain what it is." | 11368 | [679] |
| Y-C15 | "skipped" parameter → `ioSkippedIncompleteFacet` | "skipped what? maybe `ioSkippedIncompleteFacet`" | 11368 | [688] |
| Y-C16 | `InProgress` → `BeingComputed` | "InProgress => BeingComputed" | 11368 | [691] |
| Y-C17 | proactive synthesis → `trySynthesisEnumTagTypeWitness` on the synthesis path | "This should be implemented in a method named `trySynthesisEnumTagTypeWitness`" | 11368 | [690] |
| Y-C18 | `public __extern_cpp` → `export`; public is visibility, export is linkage | "`public` is a visibility modifier, it doesn't convey the semantics of "this thing needs to be preserved for final library export"." | 12242 | [916] |
| Y-C18 | `PublicDecoration` → remove | "is a historical slop that confuses `public` with `export`." | 12304 | [927] |
| Y-C19 | `shaderAbort` → `abort()` / `abortf()`, matching `printf` | "`abort()` or `abortf()` if you want to stay consistent with `printf`." | 11542 | [790] |
| Y-C19 | `...Abort...` in a generic helper → drop the feature name | "the function is nothing specific to `Abort`, why mention it in the name?" | 11542 | [843] |
| Y-C19 | `...WorkGraph...` in a generic range check → drop | "the check here is nothing specific to WorkGraph, why does the function name has WorkGraph in it?" | 11437 | [714] |
| Y-C20 | record struct types → dedicated IR opcodes via `__intrinsic_type` | "All the new types should be dedicated IR opcodes, not represented as generic struct types in the IR." | 11437 | [723] |
| Y-C21 | generic key → `IRBuiltinRequirementKey` | "this should be IRBuiltinRequirementKey. Be specific whenever you can." | 11368 | [726] |
| Y-C22 | `findBuiltinOperationKind` (bool/out) → `getBuiltinOperationKindFromString` returning an enum with `Unknown` | "This way you will only have one place to convert from operator string name to kIROp." | 11493 | [745] |
| Y-C22 | string comparison → enum comparison | "convert op to BuiltinOperatorKind first, then do enum comparison, not text comparison here." | 11493 | [757] |
| Y-C23 | shape helper → `_getBuiltinCompositeTypeShape`; promotion → `unifyBaseType` | "This should be named `unifyBaseType` IMO." | 11493 | [768] |
| Y-C23 | inline block → `substituteElementOfCompositeType(target, newElementType)` | "this should be in its own function, and named `substituteElementOfCompositeType(target, newElementType)` with proper comment documenting what the func is doing" | 11493 | [769] |
| Y-C23 | inline block → `coerceOperandsOfBuiltinBinaryExpr` | "this should be hoisted into its own function named `Type* coerceOperandsOfBuiltinBinaryExpr(leftArgExpr, rightArgExpr, out leftArgExpr, out rightArgExpr)`." | 11493 | [770] |
| Y-C24 | scattered caches → `ModuleLinkingInfo` at `IRModule::m_linkingInfo`; vague cache → `InstAnnotationMap` | "make it more explicit -- InstAnnotationMap, unless we have a second thing we want to cache." | 11517 | [776] |
| Y-C25 | attribute → `[NoDiscard]` naming convention | "let's use [NoDiscard] naming convention." | 11520 | [801] |
| Y-C26 | pack-named equality helper → `areIntValsSemanticallyEqual` | "again this func has nothing to do with pack. should named `areIntValsSemanticallyEqual`." | 11571 | [835] |
| Y-C27 | ad hoc constraint-decl test → `isConstraintDecl` | "there should be a helper named something like isConstraintDecl and we should just use that." | 11615 | [859] |
| Y-C28 | coercion-constraint text → `To(From)`, matching Slang syntax | "the string should stay consistent with the slang syntax. here it should be `To(From)`." | 11656 | [870] |
| Y-C29 | new C-API style → camel naming of `slang.h` | "It should stay consistent with the camel naming convention in slang.h." | 11948 | [897] |
| Y-C30 | loosely typed map → `Dictionary<IRDebugSource*, IRDebugCompilationUnit*>` | "so why isn't this type declared as `Dictionary<IRDebugSource*, IRDebugCompilationUnit*>` to better convey its meaning?" | 12148 | [921] |
| Y-C31 | `lookupAttributeDecl` → `lookupLegacyUnderscoreConcatenatedAttributeDecl` | "should be renamed to `lookupLegacyUnderscoreConcatenatedAttributeDecl` so we know it is legacy" | 12674 | [935] |
| Y-C32 | `coherenceID` → what is coherent? | "why is it call coherenceID? what is being coherent here?" | 9809 | [205] |
| Y-C33 | CoopMat-named vector → `WaveTangledVector` | "since this is a Vector, not a CoopMat, let's rename it to `WaveTangledVector`" | 9512 | [188] |
| Y-C34 | `TensorView` reserved for the real tensor; torch wrapper renamed | "We need `Tensor` and `TensorView` to mean the real tensor that works in slangpy and everywhere else." | 10226 | [311] |
| Y-C35 | raw-access intrinsics → `loadRaw` / `storeRaw` | "I prefer the names to be `loadRaw`/`storeRaw`." | 10609 | [384] |
| Y-C36 | `VISIBILITY_LEVEL` macros → intent names such as `TESTABLE_INTERNAL` | "They should convey more clearly what they mean, e.g. `TESTABLE_INTERNAL`." | 10609 | [385] |
| Y-C37 | reserved words `some`, `func` as test identifiers → avoid | "we should avoid using reserved keywords like `some` and `func` as identifier names in our test shaders" | 9562 | [192] |
| Y-C38 | `->` in tests → not recommended Slang syntax | "`->` is not recommended slang syntax." | 10713 | [502] |
| Y-C39 | attempt-to-read → cannot-read (diagnostic name states the rule) | "cannot-read instead of attempt-to-read" | 9788 | [473] |
| Y-C40 | `.slang-coverage` → `.coverage-mapping.json` | "I think this .slang-coverage should just be a readable json, so it should probabbly just be like `.coverage-mapping.json`." | 10886 | [535] |
| Y-C41 | separate location decoration → the inst's `sourceLoc` | "we should never need a separate location decorator." | 10886 | [530] |
| Y-C42 | new scalar enum → extend `SlangScalarType` | "We can just use SlangScalarType for this, add fb16, e4m3 and e5m2 cases to SlangScalarType instead." | 10076 | [254] |
| Y-C43 | `IComponentType::specialize()` is not IR specialization | "`IComponentType::specialize()` does not actually specialize any IR, it just generates an `specialize(...)` inst that will cause the backend to perform the actual specialization." | 10792 | [507] |
| Y-C44 | "band-aid" vs "fix" | "This is a band-aid, not a fix." | 10159 | [286] |
| Y-C45 | `T*` is not `IFoo*`: an existential is a box | "`T*` cannot convert to `IFoo*` because an existential value `IFoo` is a "box" that wraps around its implementations." | 9901 | [230] |
| Y-C46 | "is will" → "will" | "is will => will" | 9809 | [207] |
| Y-C47 | "copy" → "clone" to match IR vocabulary (reply) | "I renamed the helper API to clone terminology (`ASTCloner`, `ASTCloneContext`, `GenericSignatureCloner`, `clone*` methods)" | 11615 | [877] |
| Y-C48 | PR label spelling → `pr: breaking change` (reply) | "now `pr: breaking change`, matching CONTRIBUTING.md and the repo's actual GitHub labels (`pr: non-breaking` / `pr: breaking change`)." | 11369 | [759] |
| Y-C49 | "shader" → kernel, program, code (target-neutral) | "We should avoid using terms specific to shader." | 9732 | [3172] |
| Y-C50 | "opaque type" → bindful resource types, non-copyable types, local-only types | "Opaque type is not an accurate term for all the special types we have to deal with." | 9732 | [3174] |
| Y-C50 | "non-indexable" vs "unsized" → pick one | "We probably need to decide what terminology to use, whether or not it is non-indexable types, or unsized types." | 9560 | [3117] |
| Y-C51 | C-like layout → "natural layout" | "we call this the "natural layout"." | 9560 | [3124] |
| Y-C52 | interface-typed values → "existential types" | "this is referred to as "existential types"." | 9560 | [3121] |
| Y-C53 | `::`, `->` → `.` in canonical Slang | "Canonoical slang code should always use `.` everywhere." | 9560 | [3118] |
| Y-C54 | `const T*` → `Ptr<T, …, Access.ReadOnly>`; ReadOnly is not Immutable | "let's be more accurate here: `const` pointer is ambiguous." | 9881 | [3198] |
| Y-C54 | `&` → `__getAddress()` intrinsic on CPU and CUDA only | "Slang does not allow "take pointer" operation on any targets, particularly the & operator should be banned." | 9881 | [3190] |
| Y-C55 | D3D heap-space name → `bindlessSpaceIndex` (platform-agnostic front end) | "In the frontend, things should be named in a platform agnostic way. So we should prefer `bindlessSpaceIndex` here." | 9870 | [3183] |
| Y-C56 | two `noinline` opcodes → one `IRNoInlineDecoration` | "There is no point having duplicate IR opcodes." | 9735 | [3163] |
| Y-C57 | `[mutating]` → `this` passed by mutating borrow | "the semantic of [mutating] is to make `this` pass by mutating `borrow`." | 9560 | [3135] |
| Y-C58 | name comparison for a builtin type → `__magic_type` and `as<T>` | "Name comparison is fragile" | 9260 | [3175] |
| Y-C59 | `ConstantFoldingKind::CompileTime` → `LinkTime` for extern values | "should call with kind = ConstantFoldingKind::LinkTime instead of CompileTime, so the problem is upstream." | 9776 | [3166] |
| Y-C60 | `__member0` → a meaningful name | "why is `member0` any better than `unnamed`? can we use a better name here." | 9165 | [3084] |
### Candidate glossary changes

Status is checked against `../../slang-compiler/GLOSSARY.md` and `../../slang-language/GLOSSARY.md` as they stand today, after the bank proposals were applied. New means no entry; agrees means an entry exists and matches, with the extension noted; conflicts means an entry exists and differs. Evidence counts distinct comments or PR descriptions, and says how many are older-year.

| Term | Canonical | Avoid | Context | Author | Evidence | Status |
| --- | --- | --- | --- | --- | ---: | --- |
| Proper type | proper type (the type of a proper value; an interface or conjunction is not one, an existential box is) | value type (for this notion); bare type | language | both | 6 | new |
| Existential box type | existential box type; `dyn IFoo`; opening a box recovers the payload | existential type (bare); interface-typed value; bare interface; dynamic type | language | both | 6 | agrees: Both drafts have Existential box; add 'existential type' and 'bare' to Avoid, and 'opening' as the extraction verb. |
| Contract (interface or conjunction) | contract: the interface or conjunction of interfaces a box or constraint is over | single interface (when a conjunction is allowed) | language | Tess | 2 | new |
| Refinement | refinement (one interface refines another); refinement witness | subtype (for interface-to-interface); conformance (for interface-to-interface) | compiler | Tess | 3 | new |
| Witness | witness: the proof value for a conformance, coercion or equality; solved, never written by the user | bool plus out-parameter (for a found witness); proved (for solving a witness) | compiler | both | 4 | new |
| Requirement vs constraint | requirement (interface member); constraint or parameter (generic clause) | requirement (for a generic constraint); hidden witness requirement | language | Tess | 2 | agrees: Language draft has Requirement; add the Avoid. |
| Facet | facet: an entry in a type's flattened inheritance information, used for member lookup | — | compiler | both | 3 | new |
| Receiver | receiver (parameter): the implicit `this` parameter of a method or accessor; receiver-mode specifier | this pointer; object parameter; member function (C++) | compiler | Tess | 4 | agrees: Compiler draft has Effective `this` parameter; add 'receiver' as its name. |
| Lookup breadcrumb | lookup breadcrumb: an implicit step expression construction inserts to reach a member found by lookup (`ThisExpr`, `ThisType`) | — | compiler | Tess | 3 | new |
| Shadow (uniform-parameter) | shadow: the compiler-created declaration found by lookup under a parameter's original name (`-Gec` temporaries) | compatibility variable; source global | compiler | Tess | 4 | new |
| Abstract storage | abstract storage: a property or subscript supplied by `get`, `set` or `ref` rather than an address; abstract storage location vs memory location | location (bare) | compiler | Tess | 2 | new |
| Dialect | HLSL-flavored dialect, GLSL-flavored dialect; the HLSL dialect of Slang | HLSL mode; GLSL mode; supports GLSL; allow GLSL | language | Tess | 5 | new |
| Effective source language | effective source language; primary source file; source-language provenance; semantic include (`__include`) | AllowGLSL (as a concept) | compiler | Tess | 2 | new |
| Language version | language version; `#language slang <year>`; effective language version of a checking context | #lang; module version; dialect (for the version) | language | both | 4 | agrees: Language draft has it; add '#lang' to Avoid and the 'effective' qualifier. |
| Bytes (layout unit) | bytes; byte-granularity usage; `slang::ByteRange` | uniform (meaning bytes); uniform usage; uniform field usage; loose uniform parameters | compiler | Tess | 6 | new |
| Cumulative offset | cumulative offset | absolute offset; reflection offset | compiler | Tess | 1 | new |
| InBytes accessor suffix | `getSizeInBytes()`, `getStrideInBytes()`, `getAlignmentInBytes()` as a matched set | getStride (unitless); uniformStride | conventions | Tess | 4 | new |
| Layout unit | layout unit (`LayoutResourceKind`); size and alignment are measured per unit | kind (bare); parameter category (in prose) | compiler | Tess | 3 | agrees: Compiler draft has it. |
| Parameter-passing mode | parameter-passing mode; effective mode computed once in the front end | parameter direction; passing convention; mode spelling (for the mode) | compiler | Tess | 4 | agrees: Both drafts now use the term. |
| Borrow | borrow; borrow-in (immutable); `inout` is an exclusive mutable borrow | const ref; ConstRef; __constref (as the concept); copy-in copy-out (for inout semantics) | language | Tess | 5 | conflicts: Language draft's Parameter-passing mode cites copy-in/copy-out semantics; Tess says `inout` and `out` do not indicate copying. |
| Readonly ref access | `readonly ref` / `writeonly ref`; `const` is a legacy alias | const (as the access qualifier); constant (for read-only access) | language | Tess | 4 | agrees: Language draft has it. |
| Address space | address space (`groupshared` is a by-reference parameter in the group-shared address space) | storage class | language | both | 4 | new |
| Error (not exception) | error; raise an error | exception; throw an exception (prose); caught | language | Tess | 2 | agrees: Language draft has Error. |
| Disposition | disposition (result of a validity check) | check (as a noun for the result); bool (for the result) | compiler | Tess | 3 | agrees: Compiler draft has it. |
| Subject (of a modifier) | subject | target (for the modified construct) | compiler | Tess | 1 | agrees: Compiler draft has it. |
| Index into | index into; get an element; subscript | select from an array; array selection | compiler | Tess | 1 | agrees: Compiler draft has it. |
| Internal error | internal error (an out-of-contract shape reaching a later phase) | fallback; defensive handling; CYA default | compiler | both | 3 | agrees: Compiler draft has it. |
| Lower-to-IR | lower-to-IR; AST-to-IR lowering, a dumb mechanical translation of the checked AST | code generation (for this step); IR gen | compiler | both | 3 | agrees: Add 'code generation' to Avoid. |
| Legalization | legalization (IR passes that rewrite target-illegal shapes before emit; LegalizeSPIRV) | emit-time fix-up | compiler | both | 4 | agrees: Compiler draft has only Type legalization; generalize. |
| Front end / back end | front end (through lower-to-IR, owns validity and policy); back end (IR passes and emit, reads only the IR) | backend reading front-end options | compiler | both | 5 | conflicts: Compiler draft's Emitter entry avoids 'back-end'; both maintainers use 'back end' for the whole IR-and-emit half. |
| Dedicated IR opcode | a concept passes must recognize gets its own IR opcode (`kIROp_...`) | pattern-matching emitted asm; intrinsic name matching; generic struct type for a builtin | compiler | Yong | 4 | new |
| Post-emit metadata | post-emit metadata (`IArtifactPostEmitMetadata`): the channel for user-queryable facts about emitted code | side-band file writing; front-end reflection (for emitted-code facts) | compiler | Yong | 3 | new |
| Peephole pass | peephole optimization pass (pure simplifier, no diagnostics) | bespoke simplification pass | compiler | Yong | 4 | new |
| Specialization (not instantiation) | specialization; `Foo<Bar>` is a specialization of `Foo<>` | instantiation; template | language | Yong | 3 | agrees: Compiler draft avoids instantiation; add to the language draft's Generic entry. |
| Thread group | ThreadGroup, Wave, Thread (API scope names) | workgroup | language | Yong | 1 | agrees: Language draft has Thread group avoid workgroup. |
| Compile-time / link-time constant | compile-time constant and link-time constant (user-guide terms) | evaluation class names | language | Yong | 3 | conflicts: Language draft prefers the specification's 'translation-time constant' for the whole class; Yong cites the user guide. |
| static const (not constexpr) | `static const` means compile-time evaluation; `constexpr` is unfinished and undocumented | constexpr (in user docs); volatile | language | Yong | 2 | new |
| Extension (not struct extension) | extension; generic extension | struct extension | language | Yong | 2 | agrees: Language draft has Extension. |
| enum (not enum class) | `enum`; `enum class` is a C++ compatibility spelling | enum class (in the core language spec) | language | Yong | 1 | new |
| public vs export | `public` is visibility; `export` is linkage | public __extern_cpp; PublicDecoration | language | Yong | 2 | new |
| internal (visibility) | `internal` for core-module declarations not callable by users; `__`-prefixed names are unsupported API | documenting __ functions | language | Yong | 2 | new |
| Experimental module | experimental features live in `experimental/*.slang`, imported explicitly | experimental code in core.meta.slang | compiler | Yong | 1 | new |
| Capability join / implies | join of capability sets; an atom implies (inherits from) another; a true disjunction is unrepresentable | merge; union (when join is meant) | compiler | Yong | 3 | agrees: Extends Capability set. |
| Capability interface (numerics) | capability interface (`IScalarNumeric`); capability conjunction alias; dispatch marker (`__Builtin...`) | capability (bare, when an interface is meant) | language | Tess | 3 | conflicts: 'Capability' already names the target-feature system; the numerics docs reuse the word for interfaces. |
| Logical scalar / Mask | logical scalar (`T.Scalar`); mask (shape-preserving comparison result) | — | language | Tess | 2 | new |
| Semantic name / semantic index | semantic name (never ends in a digit) and semantic index; `SV_` system-value semantics | semantic (bare) | language | Tess | 2 | agrees: Extends Binding semantic. |
| Argument vs parameter value | argument value (what is passed); parameter (what is declared) | parameter value (for an argument) | conventions | Tess | 2 | new |
| Default-value expression | default-value expression; default generic argument | default expression; real default | compiler | Tess | 3 | new |
| Frontier (overload) | candidate frontier: tied overload candidates after ordinary ranking | — | compiler | Tess | 2 | new |
| Sub / sup type | sub and sup type of a constraint | endpoint | compiler | Yong | 2 | new |
| Publication (synthesized declarations) | publication; synthesized declaration root; whole-module phase | — | compiler | Tess | 1 | new |
| Documentation comment / implementation comment | documentation comment (client contract, `///` or `//` on a declaration); implementation comment (strategy, in the body) | mixing the two audiences; dirty laundry | conventions | Tess | 4 | new |
| Early-out | early-out (asserted or justified) | cowardly early-out test; CYA guard | conventions | Tess | 3 | new |
| Predicate | predicate: a named Boolean helper that states the exact condition | compound conditional | conventions | both | 3 | new |
| Bottleneck | bottleneck (one routine every duplicate flows through) | copy-paste coding | conventions | Tess | 3 | new |
| Accessor verbs | `get` cannot fail; `find` searches; `try`/`tryGet` may fail; `calc`/`compute` for work; `maybe`/`IfNeeded` for conditional action | get (for failable or expensive) | conventions | Tess | 5 | new |
| Acronym casing | acronyms entirely upper or entirely lower case (`UserID`, `defaultMDFileName`) | UserId; Md | conventions | Tess | 1 | new |
| Slang type names | `UInt8`, `Int32`: UpperCamelCase builtin type names | uint8_t-style names as canonical | conventions | Tess | 1 | new |
| Review vocabulary | band-aid, code smell, CYA, cowardly, carve-out, hackery, kludge, slop, dirty laundry, sweep under the rug, WAR | — | review vocabulary | both | 8 | new |
| Type conformance test input | `//TEST_INPUT: type_conformance Impl:IFoo = <type id>`; runtime type ids from `SV_DispatchThreadID` | baked constant type ids | conventions | Yong | 3 | new |
| Standard module library | monolithic vs separate standard-modules library; compiler-embedded; `slang-embedded-standard-modules` | embedded (bare) | compiler | Tess | 2 | agrees: Extends Standard module. |
| Natural layout | natural layout: Slang's platform-neutral default layout; size is not rounded up to alignment | C layout (for the default); compatible (for C-like modes) | compiler | both | 5 (2 older year) | conflicts: Yong wants natural layout made C/C++-consistent; Tess wants C-like layout only on explicit request and never called 'compatible'. |
| Take address | take the address of (the `&` operation); `__getAddress()` intrinsic | take pointer | language | Yong | 2 (1 older year) | new |
| Immutable vs read-only | immutable = read-only plus exclusive (an optimizer contract); read-only = access permission only | immutable (when only read-only is checked) | compiler | both | 4 (3 older year) | new |
| Casting vs conversion | cast (explicit) versus conversion (implicit) | cast (for an implicit conversion) | language | Tess | 1 (1 older year) only | new |
| Combined texture-sampler pair | combined texture-sampler pair | combined texture sampler | language | Tess | 1 (1 older year) only | new |
| Size in bytes vs count | offset and size in bytes; index and count in elements; strings report size in bytes | length (for byte size); byte count; characters (for Slang strings) | conventions | Tess | 4 (4 older year) only | new |
| Pointee | pointee type of a pointer | target type (of a pointer) | compiler | Tess | 1 (1 older year) only | new |
| Unit type | unit type (compiler prose for `void`) | — | compiler | Tess | 2 (1 older year) | conflicts: Older year prefers 'unit type' inside the compiler; in 2026 she chose 'non-void proper type' over 'non-unit'. |
| Kernel target vs host target | kernel target (CPU code emitted for shader kernels) versus host target | CPU target (bare, when the distinction matters) | compiler | Yong | 1 (1 older year) only | agrees: Older year only; language draft's Kernel entry is compatible. |
| Descriptor kind names | SampledImage, StorageBuffer, UniformTexelBuffer, ConstantBuffer (Vulkan descriptor names) | Texture_Read; Buffer_ReadWrite | compiler | Yong | 3 (3 older year) only | new |
## (b) Tess's rules

The bank report stated R1 to R18 from 231 inline threads. GitHub adds 1,427 recent-year comments, so every bank rule is re-attested here with new quotes. New rules start at R19. Quotes are at most 25 words; `[n]` is the comment index and the PR number follows.

### Bank rules re-attested on GitHub

Each bank rule keeps its number; the quotes below are new and did not appear in the bank report.

- **R1. Every early-out is an assertion or carries a justification.** "An early-out like this fundamentally necessitates a comment explaining the rationale for why we need to, or can, early-out." [1205] PR 11135; "Please either assert the expected condition rather than just hope for it, or provide a much stronger explanation" [2487] PR 13401; "I'm left unclear on whether the condition that's being worried about here can actually occur." [2296] PR 13539
- **R2. Assert invariants; never default silently.** "Assert your preconditions/invariants; do not just test for them and then bail, making it somebody else's problem." [1438] PR 12585; "The `default` here should be an assertion failure, not a CYA "safe" response." [2343] PR 13406; "Real defensive code starts with asserting your assumptions and invariants." [1211] PR 11135
- **R3. Documentation comments state the client contract; implementation comments explain strategy.** "Documentation comments should always be written for the sake of the client/consumer of the abstraction, and never for the sake of the implementer" [1511] PR 12596; "Implementation strategy belongs in implementation comments." [1399] PR 12421; "Restrict documentation comments to what the meaning and/or behavioral contract of an abstraction is." [2386] PR 13885
- **R4. No process or history in code.** "Stop adding *process* information (e.g., issue/PR numbers) as documentation in the codebase." [2479] PR 14115; "Comments should primarily speak to the system as it *is* and not constantly reference back to plans/issues/tasks" [1489] PR 12568; "As a general guideline, do not reference specific issues in documentation." [1904] PR 13113
- **R5. Comment voice: declarative, authorial "we", full sentences, for a new contributor.** "I have no idea where this obsession with imperative sentences is coming from, but it needs to stop." [2135] PR 13116; "The audience for an implementer-facing comment like this should always be some future contributor, years in the future" [2125] PR 13445; "Please avoid personifying objects/values like this, unless there is good reason." [2170] PR 13445
- **R6. Every pass, file, and non-trivial routine opens with problem, strategy, and rationale.** "Where is the block comment at the top of this file explaining the purpose of the pass, the invariants it relies upon" [1201] PR 11135; "Explain the context (the problem or task at hand), the strategy we employ, and the rationale for why we do it that way." [2132] PR 13445; "the implementation needs to teach future contributors how to think about the solver, not just provide a long list of routines" [1251] PR 11210
- **R7. Names say exactly what a thing does or is.** "Name things what they *are*." [1239] PR 11210; "I'd rather have an extremely verbose name that actually says what the function does" [1214] PR 11135; "The name of a procedure should say what it *does*." [1203] PR 11135
- **R8. Accessor verbs and Boolean names follow convention.** "`get...` functions should be accessors that cannot fail (on input that is well-formed), while a `find...` function should be used for the failable case." [1421] PR 12585; "this function may fail and is not a simple accessor, so a `tryGet` name would be more appropriate here" [1246] PR 11210; "This should be `getStrideInBytes()`." [1367] PR 12306
- **R9. Compound conditions become named predicates; early-outs go one per statement.** "As soon as a you have more than 2 cases in a chain of `||`/`&&` you have ugly code that needs to be re-thought." [1475] PR 12575; "There is no case where a giant complicated conditional expression is acceptable." [2129] PR 13445; "Well-named helper methods are vital for making the actual condition that is being tested something humans can understand." [1180] PR 10034
- **R10. Repeated logic bottlenecks through one named helper.** "If you find yourself writing the same predicate more than once, that's a strong indication that it should be factored out into a subroutine" [2050] PR 13213; "Thus `CheckProperType` is *the* logical bottleneck for this validation." [1698] PR 12876; "It is a huge code smell that this same three-line sequence is being copy-pasted" [1346] PR 12131
- **R11. Return and store meaningful types.** "You didn't find a `bool`; you found a witness." [1227] PR 11210; "This boolean is carrying too much hidden state-machine meaning." [1275] PR 11210; "Almost any query that is throwing away information (in this case, throwing away the cast(s), if there were any) is a bad sign." [1248] PR 11210
- **R12. Fix the producer; keep one canonical representation; consumers never patch.** "This is not a fix for the root cause of the issue." [1137] PR 9360; "The fix is producer-side: semantic checking now rejects a global atomic counter" [1758] PR 12836; "doing a `findModifier` for any of the parameter-passing-mode modifiers, it is 90+% likely to be incorrect or a bug waiting to happen." [2473] PR 11709
- **R13. IR edits create new instructions; inlining is a last resort.** "As a general rule we should be *very* careful about going in and changing the types/operands/etc. of existing instructions, instead of creating *new* instructions" [2302] PR 13539; "the idiomatic policy on the Slang project is to create a specialized clone of the callee where the body can be specialized" [2449] PR 14081; "Using `replaceUsesWith()` on a type is always a slightly scary thing to do." [1086] PR 8754
- **R14. Flat code: early-outs first, `switch` over if-cascades.** "I strongly object to you taking existing flattened control flow and turning it into this deeply-nested mess." [1437] PR 12585; "Use a `switch` here on the opcode, and not a frustratingly complicated conditional expression." [1482] PR 12575; "I tend to prefer a `switch` over an `if` for the precise reason that they are easier to extend with more cases" [1109] PR 8960
- **R15. Stay in scope and respect recorded intent.** "You rewrote a lot of code in response to my last review round that I didn't ask you to change..." [1504] PR 12568; "Don't go deleting high-quality human-authored content without extremely strong reasoning." [2391] PR 13885; "This carve out should not have been added without consulting a human designer/architect." [1441] PR 12585
- **R16. User guide shows the happy path; the reference holds every detail; neither cites the tracker.** "The kind of commentary I was proposing belongs in the reference." [2203] PR 13460; "we want to tell the user what they need to know, and not mire them in implementation details" [1338] PR 11135; "Please don't bog down the experience for users who actually want the Slang language for the sake of users who need the HLSL dialect" [2225] PR 13506
- **R17. Tests exercise the feature; self-review before posting; ask before writing a workaround.** "You should always be applying the clarity-oriented review criteria to your work as a self-review, and iterating until they don't surface any issues." [1514] PR 12596; "I am not adding a test that would give false coverage confidence." [1575] PR 12835; "Otherwise this test would still pass if the solver failed earlier for a much less interesting reason." [1260] PR 11210
- **R18. Magic numbers become named constants; invariant-bearing state is private.** "Magic numbers should become named constants." [1396] PR 12421; "Please put those tag-dependent invariants behind the type boundary." [1262] PR 11210; "Should this really be public? Why?" [1534] PR 12715

### New rules from GitHub

#### R19. Define every term before use; never coin a term the codebase already names

Rule: a new concept gets a precise definition where it is introduced, usually in the file header. An existing concept keeps its existing name, codebase-wide.
Example: a solver that introduces "slots" defines a slot in the introductory block; it says "argument value", never "parameter value".
- "Terminology should be defined before it is used." [1233] PR 11210
- "Stop inventing terminology when there is established precedent in the codebase." [1245] PR 11210
- "I also think we need to land on a single term that we will use consistently across all of these queries" [1409] PR 12585

#### R20. Slang has its own vocabulary and casing; do not import C or C++ words

Rule: Slang types and concepts use Slang names (`UInt8`, method, proper type, error), not `uint8_t`, member function, or exception. Acronyms are all upper or all lower case.
Example: a comment says "methods declared on a value type", and an identifier is `defaultMDFileName`.
- "Slang is not C++! We should not default to C++ terminology just from inertia!" [2215] PR 13506
- "I will continue to push back on using C/C++ concepts and terminology for stuff in Slang, whenever possible." [1117] PR 8960
- "acronyms/initialisms should always appear either entirely in upper case, or entirely in lower case (e.g., `UserID` instead of `UserId`)" [1159] PR 10554

#### R21. The front end owns validity and policy; the back end reads only the IR

Rule: semantic validity, target-support checks, and layout policy are decided in the front end. IR passes and emitters never read front-end options or re-derive semantics.
Example: a target-unsupported parameter mode is rejected during checking, not in an IR pass or the emitter.
- "Any code in the compiler back-end accessing compiler options that were intended for the front-end is buggy by definition." [1864] PR 12836
- "IR passes really aren't the right place to insert validation logic anyway" [1472] PR 12575
- "Invoking the front-end layout rules from within back-end logic (IR linking and beyond) should be considered a strong design smell." [1521] PR 12544

#### R22. Implement the obvious lowering instead of diagnosing a restricted case

Rule: a mode or feature that restricts an already supported one is implemented by the obvious lowering, not banned with a diagnostic.
Example: a read-only reference mode lowers like `ref` with fewer permissions, so autodiff supports it rather than rejecting it.
- "wasting a lot of time/energy/code on trying to diagnose use of the newly-added modifiers rather than just implement them in the obvious ways." [1487] PR 12575
- "they are both restrictions of what `ref` allows, so should be easier to support with differentiation, not harder" [1462] PR 12575
- "Let's just lower them to the obvious things and then not have to diagnose." [1487] PR 12575

#### R23. Be systematic: follow a new representation through every consumer, and never overload an existing node

Rule: a new class of type or expression gets mangling, lookup, printing, and lowering; new semantics get a new `Expr` or synthesized attribute.
Example: adding an existential-box type adds its mangling case the same day, and boxing gets `MakeExistentialBoxExpr`.
- "When adding a new class of type to the Slang compiler, implementing mangling for that new class of type is part of what is required." [1408] PR 12555
- "Let's not overload the semantics of any existing AST classes, since the whole point of this refactoring is to make things more clean, explicit, orthogonal," [2384] PR 13885
- "Part of being systematic is following through on the consequences of the initial change..." [1408] PR 12555

#### R24. Every taxonomy will grow; state assumptions as contracts and assert the unhandled case

Rule: no unstated closed-world assumptions, no two-state values that will gain a third state, and an asserting `default` for unhandled cases.
Example: a classification over parameter modes lists all current modes and asserts on an unknown one.
- "writing brittle code that makes *unstated* implicit assumptions about what is and is not in scope for the entire future of the project" [2391] PR 13885
- "My experience is that every two-state thing in the universe eventually gains more options and causes messes." [2093] PR 13371
- "have a catch-all `default` that asserts, so that we know we are handling all the cases that can actually arise" [1378] PR 12310

#### R25. Diagnostic text is literally accurate and names the specific construct

Rule: a message describes exactly the code it fires on, names the construct, and states the positive rule rather than a vague category.
Example: "expression cannot be used as a statement" instead of "this form is not allowed here".
- "the diagnostic message is quite literally inaccurate to the code it is diagnosing should be seen as a code smell / warning sign" [1406] PR 12555
- "Just having a general "a type or namespace" is both unhelpful and inaccurate." [1450] PR 12585
- "Something like: "expression cannot be used as a statement"" [1448] PR 12585

#### R26. A hack is labeled as a hack, with the real rule stated beside it

Rule: compatibility hacks survive only with a comment saying forthrightly that the type system does not justify them and that they set no precedent.
Example: an artificial conformance witness carries "necessary compatibility hack, not a precedent".
- "I want us to be *very* aware of when we are committing hackery in the name of maintaining compatibility" [2393] PR 13885
- "This class is a necessary compatibility hack, and should not be seen as a precedent to excuse further unfounded conformance relationships." [2388] PR 13885
- "this code merits a `TODO` comment noting that the check is not only ugly, but is one that we should aspire to remove" [1907] PR 13113

#### R27. Accessors own `ensureDecl`; a bare call elsewhere is a smell

Rule: the accessor that reads checked data ensures the required check state itself. Passive operations assert the state instead of calling `ensureDecl`.
Example: `getEffectiveThisParamInfo` ensures `SignatureChecked`; its callers never call `ensureDecl`.
- "There should be *very* few cases where code ever needs to `ensureDecl` manually, outside of some accessor, because the accessors themselves should be responsible" [2231] PR 13506
- "Bare `ensureDecl` calls being added in random places is a code smell, indicating that accessors are being defined/used that don't properly ensure the state" [2070] PR 13232

#### R28. Never demote a decl-ref to a bare declaration in semantic checking

Rule: substitutions travel with the decl-ref. Collapsing to `Decl*` needs a documented, enforced invariant that nothing was lost.
Example: a solver keys its table on the decl-ref, or proves the generic chain has one level before using the `Decl*`.
- "It is good practice to never demote from a decl-ref to a plain declaration in semantic-checking logic" [1222] PR 11210
- "the code asks for context-preserving information and then silently assumes the raw declaration is a unique solver key." [1277] PR 11210
- "This should be doing a dynamic `as` cast of the *decl-ref* and not just the declaration." [1222] PR 11210

#### R29. Dialect leniency is opt-in, decided by the call site's language, and still warns

Rule: HLSL-dialect permissiveness applies where the call appears and downgrades errors to warnings. Rejecting code that was always wrong is a bug fix, not a breaking change.
Example: calling a mutating method on an immutable receiver warns in HLSL files and errors in Slang files.
- "We should be making that decision based on the language where the call appears" [2426] PR 13966
- "We should continue to diagnose the situation with a warning (just downgrade the current error to a warning for the HLSL dialect)" [2427] PR 13966
- "those users deserve to have their code break, and they will thank us for catching their mistakes." [2367] PR 13406

#### R30. Public API additions are new, obviously correct entry points sized to demonstrated demand

Rule: a new feature gets its own API, never an overloaded existing one. Complexity must match demonstrated demand, and major features start as proposals.
Example: byte-range usage queries get a new interface instead of a tri-state return bolted onto a Boolean API.
- "Please don't hijack existing API entry points and bolt on tons of new complexity to try and support a new feature that is ultimately orthogonal" [1321] PR 11135
- "so long as the amount of code complexity added is commensurate with the *demonstrated* breadth of developer demand for such a feature." [1322] PR 11135
- "The official-on-paper process for doing major evolution of the language and builtin modules is to open a PR to add a proposal" [1088] PR 7496

#### R31. Write the contract top-down, then directed tests with hand-checked results

Rule: the normative API contract and its terminology come first; names, docs, types, and tests follow it. Test baselines are assertions, never captured output.
Example: a usage API states its model, then each test lists the byte ranges it expects and why.
- "Please define this contract top-down and use its terms consistently in API names, documentation, implementation types, and comments." [1355] PR 11135
- "Write the normative API contract and directed expected results first." [1365] PR 11135
- "audit every test baseline as an assertion of intended semantics rather than accepting whatever the compiler emitted" [1365] PR 11135

#### R32. Implementation comments narrate: set up the task, then interleave with the code

Rule: an explanation states the task at hand, then threads strategy and rationale through the code one to four lines at a time, ending in "if X, then Y, because Z".
Example: before each `if`, one sentence says which case it handles and why that handling is correct.
- "Always prefer a narrative flow where each little bit of comment helps set up the reader to understand why the next 1-4 lines" [2136] PR 13116
- "Slow down and actually set up the problem/task at hand first. What are we being asked to determine here?" [2136] PR 13116
- "I would expect something like an "If ... then ... because ..." sort of construction" [1673] PR 12136

#### R33. User input gets a graceful diagnostic; only internal invariants assert

Rule: a shape a user can write is diagnosed and recovered from. Assertions are for shapes the compiler itself guarantees impossible.
Example: an unsupported layout in user code reports an error; an unlowered helper type at emit asserts.
- "we should gracefully diagnose such a case and then move on" [2411] PR 13958
- "why wouldn't the API just return a `true` result in that case, rather than force the complexity back on the user?" [1317] PR 11135
- "being "fail fast" and diagnosing an issue at the earliest possible point allowed is not always the approach that leads to the best user-facing diagnostics" [1372] PR 12252

#### R34. Agent-authored code meets the human bar, and agents fix their own review skills

Rule: bad comments are smoke for bugs; agents run the clarity self-review, never write "safe" guards, and update the review skills when a rule is missed.
Example: an agent that is told about a missing rule opens a PR revising the review skill, then re-reviews its own diff.
- "Bad comments are smoke, and I find that there's almost always fire to go along with it." [1249] PR 11210
- "please put up a PR to revise those review skills with the necessary details about the purpose/role of comments." [1514] PR 12596
- "We've got to fight against the tide of bad advice from coding agents trained on bad code." [1211] PR 11135

### Other directives seen once or twice

- Layered IR accessors: an operand accessor, then a value accessor that asserts the shape. "The usual rule/practice for IR instruction accessors like this is to factor them into two parts: an accessor that returns the appropriate *operand*" [1351] PR 11135
- No locale-sensitive `ctype.h` functions. "Use of the standard C `isdigit` and related character classification functions from `ctype.h` is not allowed in the Slang codebase, for good reason." [1128] PR 9365
- A new IR pass is its own `.h/.cpp` pair. "When introducing a new Slang IR pass, please define it as its own standalone .h/.cpp pair" [2085] PR 13178
- Backward peepholes belong in the general simplifier. "This seems like a transformation that can/should be folded into the more general-purpose simplification passes" [2448] PR 14081
- Parameter-mode pointer types appear only on `IRParam`s. "the special pointer types that represent parameter-passing modes are intended to only be used on the `IRParam`s themselves" [1086] PR 8754
- Core-module meta comments go inside `${...}`. "the comment here being *outside* the `${...}` means that it will end up in the generated `.slang` output" [1678] PR 12765
- Grammar additions go through `SyntaxDecl` tables. "rather than hacking it here deep in the parser." [1498] PR 12568
- Diagnostic text comes from the data-driven definitions. "It is bad form to have this much of the human-readable diagnostic message be coming from the compiler implementation itself, rather than the data-driven definitions" [2476] PR 11709
- Lines are free; readability wins. "There is not a line shortage going on. We can spare extra lines in order to make our code more readable and clear." [2090] PR 13178
- HLSL tests are `.hlsl` files. "are there reasons for why these tests are being authored as `.slang` files and then using `-source-language`, rather than using `.hlsl` files" [2122] PR 13445
- Deprecated options get an ugly name. "rename `CompilerOptionName::AllowGLSL` to something suitably ugly like `DEPRECATED_LegacyAllowGLSL_DO_NOT_USE`" [1863] PR 12836
- `closes #n` only when the PR truly closes it. "writing "closes #..." in a PR description can trigger GitHub's auto-close mechanism when a PR lands" [1403] PR 12555
- Review skills never `APPROVE`. "the skill really should provide explicit criteria under which it should fall back to `COMMENT`, and note that it should never use `APPROVE`." [1308] PR 11340
## (c) Yong's directives

The bank had thirteen Yong threads and stated Y1 to Y11. GitHub adds 895 recent-year comments on 218 PRs, 487 of them on other people's PRs. His comments are short (median 24 words), so one directive often rests on a single sentence. Each directive below is a plain rule, then the ask he made, then quotes. "Same as" names the Tess rule when the two agree.

### Bank directives re-attested

- **Y1. A helper type that exists only to be lowered must never reach emit.** "It shall be explicitly lowered to `uint` during the legalization steps at some point, and not being visible to the emit logic." [895] PR 11798; "They should all have `__intrinsic_type` attribute at their declration that maps them into dedicated IR opcodes." [719] PR 11437. Same as Tess R12.
- **Y2. A round-trip cast simplifies to its inner operand in the peephole pass.** "should add cases for uint2/64->DescriptorHandle casts here, and just return inner operand." [920] PR 12263; "The most reasonable place to run this check is in PeepholeOptimize pass" [213] PR 9814.
- **Y3. No use-chasing without a failing test.** "Not sure why we need to chase the uses here. Which test will break without this?" [912] PR 12080; "What is broken without it?" [909] PR 12195; "do we still need the traverseUsers call here?" [777] PR 11517. Same as Tess R1.
- **Y4. Assert what an earlier stage already makes impossible.** "should this be an assert instead, now that parsing is already making this impossible?" [914] PR 12252; "should assert countLit == 1, we can't handle other cases here." [274] PR 10121; "this is guaranteed to be non-null by the frontend." [245] PR 10059. Same as Tess R2.
- **Y5. Mirror the sibling case; put the version-specific check first.** "should be fine to just `return getDeclVisibility(parentAggTypeDecl)` here to mirror the interface case above." [906] PR 12151; "Have we looked at similar situations with `MakeMatrixFromScalar`, `MakeArrayFromScalar`, `MakeMatrixFromVector` etc?" [521] PR 10883.
- **Y6. Combine inputs first, then compare once through a single utility.** "should we compute a join of all the specified `-capability` atoms first into a CapabilitySet" [900] PR 12122; "That way we have a single loop that can check for all sorts of invalid things in parameter blocks." [551] PR 10981. Same as Tess R10.
- **Y7. Gate vendor opcodes on the user's capability and on the resource kind.** "we produce this ir op code only when spvBindlessTextureNV is selected in the core library's `__target_switch`." [280] PR 10177; "This is the kind of error to be captured by the capability system, not by static assert / ir checking." [653] PR 11310.
- **Y8. Pin the language version in a version-sensitive test.** "should have an explicit `#language slang 2025` declaration here to pin the user module version in the test." [904] PR 12151.
- **Y9. Declare containers and results with the exact types they hold.** "so why isn't this type declared as `Dictionary<IRDebugSource*, IRDebugCompilationUnit*>` to better convey its meaning?" [921] PR 12148; "this should be IRBuiltinRequirementKey. Be specific whenever you can." [726] PR 11368; "Always use DeclRef if you mean a reference to a decl." [814] PR 11571. Same as Tess R11.
- **Y10. Document what a spelling means in each language version.** "should also note that `(,...,)` in slang 2026 or later means tuple construction." [893] PR 11953; "In slang 2026 or later, (a, b) evalutes to a tuple." [581] PR 11194.
- **Y11. Deprecate now what a future version will remove.** "We should make it clear that UnscopedEnum is to be removed in a future language, and we need to deprecate it now." [557] PR 11044; "should be renamed to `lookupLegacyUnderscoreConcatenatedAttributeDecl` so we know it is legacy" [935] PR 12674. Same as Tess R16.

### New directives from GitHub

The three most repeated are Y12, Y13 and Y15.

**Y12. Fix the stage that produced the bad shape; lowering and emit never repair it.**
Plain English: if the compiler crashes late, the bug is early. Lowering is a dumb translation of what checking decided; emit is a dumb printer of the IR.
Ask: move the fix into the type checker or a legalization pass, and delete the late patch.
- "This is a band-aid, not a fix." [286] PR 10159
- "If the declrefs are wrong, the fault is in the type checker, not in the lower to ir logic." [286] PR 10159
- "The SlangIR should be transformed into the right form before hitting emit." [369] PR 10527
- "If you need to go in great length discovering high level info like inheritance hierarchy during lower-to-ir, the design is wrong." [517] PR 10850
- "Something is wrong upstream." [720] PR 11437
Same as Tess R12 and R21.

**Y13. Reuse the mechanism that already exists; never add an ad hoc check beside it.**
Plain English: before writing a new rule, find the general facility that handles that class of rule and add a case to it.
Ask: route modifier conflicts through `conflictGroup`, call the existing helper, put capability metadata in the capdef file.
- "There is already a generic modifier conflictGroup mechanism for this purpose." [560] PR 11048
- "We should not have more than one place where we define this kind of metadata about capabilities." [211] PR 9777
- "can just call `isValidCompileTimeConstantType` here too." [309] PR 10034
- "Every time we are adding ad hoc logic, we should question whether we are doing things wrong." [2354] PR 13406 is Tess's version of the same rule.
Same as Tess R10 and R12.

**Y14. A concept that passes must recognize gets its own IR instruction; never rediscover it by pattern matching.**
Plain English: give the thing a name in the IR. Later passes then look for that name instead of guessing from text, decorations, or call shapes.
Ask: add `kIROp_CoopMatMulAdd`, `kIROp_ImageLoad`, `kIROp_NullDescriptorHandle`; encode texture format in the type.
- "map the coopMatMulAdd call to an new kIROp_CoopMatMulAdd instruction, that we can easily identify this instruction in the IR" [291] PR 10076
- "Instead of using this adhoc logic to identify a image load/store call, we should introduce kIROp_ImageLoad/kIROp_ImageStore instructions" [554] PR 11090
- "All the new types should be dedicated IR opcodes, not represented as generic struct types in the IR." [723] PR 11437
- "This is not reliable, especially when debug info is absent for any reason." [526] PR 10886
Same as Tess R12 (one canonical representation) and R23.

**Y15. A test must exercise the real path: runtime values, one condition at a time, every applicable target, and a negative check.**
Plain English: a test that the optimizer can fold away proves nothing. Check what must not appear as well as what must.
Ask: take type ids from `SV_DispatchThreadID`, split tests per condition, run on all targets, add `HLSL-NOT:` lines.
- "This test is not actually exercising dynamic dispatch because the type for every variable is compile-time constant after specialization." [236] PR 9917
- "always use a runtime value instead of baked constant literal for type ids." [257] PR 10089
- "this test is not specific to vulkan so we should run it on all targets." [263] PR 9628
- "the test should be written in a way that we test for one condition at a time." [247] PR 10017
- "should use HLSL-NOT: to ensure testMissingTexture isn't appearing in the resulting hlsl." [277] PR 10121
Same as Tess R17.

**Y16. Public COM interfaces are append-only; new methods go to a versioned interface or the end.**
Plain English: callers compiled against an older header must keep working, so never reorder or insert.
Ask: add to `IComponentType2`, or append at the end; keep new free functions outside `ISession`.
- "new additions should be added to `IComponentType2` to avoid ABI breakage." [190] PR 9707
- "this needs to added at the end of the interface to avoid ABI breakage." [195] PR 9707
- "This allows us to extend the interface in the future without modifying the COM interface." [539] PR 10886
Yong only; Tess R30 covers the design side of public APIs.

**Y17. Shared code assumes no single target's layout.**
Plain English: a size or representation that is true on Vulkan may be false on CUDA; write the general case or branch on the target.
Ask: do not assume a descriptor handle is `uint2`; make metadata target-neutral; test cpp, cuda, llvm and spirv.
- "Again, do not assume descriptor handle is uint2, unless you are in a spirv-only path." [238] PR 9940
- "I don't think this should be specific to SPIRV target." [290] PR 10076
- "we need to make sure this works on cpp, cuda, llvm, spirv targets." [229] PR 9901
Yong only.

**Y18. Keep the compiler simple and cheap; gate optional work so common compiles pay nothing.**
Plain English: do expensive work once, cache it, and skip passes whose trigger is absent.
Ask: call `_coerce` once and reuse the result; compute once on `getShared()`; run a validation pass only when its opcode is present.
- "Should just call _coerce once here, and reuse the cost and resolved declref for code generation and error reporting." [264] PR 9628
- "then only run validateBarrierFlagsForHLSLInst when the bit is set, so we don't slow down all hlsl compiles." [892] PR 11437
- "I lean towards keep things simpler in the compiler so we don't put too much stress on compile times." [383] PR 10541
- "we should avoid adding new passes if possible to keep the top level simple." [712] PR 11423
Yong only.

**Y19. Maintenance burden gates features; dependencies are optional and binaries stay lean.**
Plain English: a low-priority feature that makes the code harder to keep is declined, and a heavy dependency must be switchable off.
Ask: make the cmark dependency optional; disable the feature for WebAssembly; clean tech debt before extending it.
- "if a feature is P2 and supporting it means making the code harder to maintain, then we shouldn't do so." [186] PR 9365
- "It may be necessary to make this dependency optional" [372] PR 10554
- "For WebASM builds we may need to disable the feature to keep the binary lean." [373] PR 10554
Yong only.

**Y20. User docs use the codebase's terminology and omit unfinished features.**
Plain English: documentation says "specialization", "ThreadGroup" and "static const", and stays silent on `constexpr`.
Ask: replace "instantiation" with "specialization"; drop `constexpr` and `volatile` from the reference.
- "I would prefer "specialization" over "instantiation" as the terminology, because specialization is what is being used in the codebase and in existing docs." [302] PR 10165
- "Let's not mention constexpr right now, it's not done and not ready for end-user use." [376] PR 10455
- "these `__` functions are not officially supported API and should not appear in our public documentation." [547] PR 11009
Same as Tess R16 and R19.

**Y21. Data a user may query goes into post-emit metadata behind a dedicated API; never side-band files.**
Plain English: the compiler reports facts through its API, not by writing files on its own.
Ask: add a `coverageTracing` field to the metadata and a query for it.
- "Never do side-band file writing. This is not allowed in the compiler. Never do this please." [527] PR 10886
- "any data that we need the user to be able to query should go into the post emit metadata with dedicated API to query it." [527] PR 10886
Yong only.

**Y22. Design for programs with many modules.**
Plain English: an id or synthesized declaration that is unique per module will clash when modules are linked.
Ask: give statements program-wide ids and declare synthesized buffers once.
- "If a program contains more than one module, the uids for statements in different module would clash." [531] PR 10886
- "This means that every module will contain its own declaration of the buffer parameter." [540] PR 10886
Yong only.

**Y23. Encode semantics in the type or a dedicated opcode, never in decorations, name hints or member state.**
Plain English: information that passes may drop must not carry meaning.
Ask: make the format a generic argument of the buffer type; reference `IRDebugSource` as an operand; no emitter "global variable".
- "there are just too many places throughout our backend that cannot recognize an `IRAttributedType` or just randomly drops the attributes" [809] PR 11460
- "can we just make IRDebugCompilationUnit contain operands that references the IRDebugSource insts?" [922] PR 12148
- "instead of relying on this "global variable" for communication." [748] PR 11512
Same as Tess R12.

**Y24. Shared caches live in one class under a mutex, and thread safety is proven.**
Plain English: anything two compiles can touch at once needs a lock and an argument for why it is safe.
Ask: wrap cached state in `ModuleLinkingInfo`, protect its build with a mutex, prefer a read-write lock over invalidation.
- "The build of the linking info object should be protected by a mutex." [775] PR 11517
- "how do we know if this is safe from race condition? need to prove it." [778] PR 11517
Yong only.

**Y25. Diagnostics have a readable fallback for every case, adapt to the construct, and print Slang syntax.**
Plain English: no unsatisfied constraint may produce a blank or mystic message.
Ask: one shared printer; `To(From)` spelling; the operator text adapts to the constraint kind.
- "This needs to be the fallback message for all unsatified constraints." [863] PR 11656
- "the string should stay consistent with the slang syntax. here it should be `To(From)`." [870] PR 11656
- "This error message is confusing and mystic, and this should be treated as a bug that we need to fix separately." [268] PR 10075
Same as Tess R25.

**Y26. Generalize rather than restrict; remove conditions that are not necessary.**
Plain English: handle the whole class of inputs, not the one case that broke.
Ask: handle any witness-table entry, not only `IntLit`; apply a translation unconditionally.
- "The fix is likely too conservative." [556] PR 11061
- "this type translation shouldn't be specific to use of descriptor heap and should take place unconditionally." [563] PR 11211
- "the IR code generalized to handle more than just IntLits, because it doesn't occur to me that they are necessary restrictions." [520] PR 10854
Same as Tess R12 (whole space of shapes).

**Y27. Invalid constructs get a language-level diagnostic; invariants are asserted, never guarded.**
Plain English: say no to the user loudly, and crash loudly on compiler mistakes; never limp on.
Ask: diagnose address-of-local; make an impossible target switch an error; delete null guards on `Val` operands.
- "In general, this is disallowed by the slang language and we should have a diagnostic for it." [231] PR 9901
- "something is already catastrophically wrong, so this will simply kick the can down the road." [392] PR 10615
- "any failures in a stage (lex,parsing,checking,ir-lowering) should prevent the next stage from running." [917] PR 12252
Same as Tess R2 and R33.

**Y28. Non-trivial inline logic becomes a named, commented function; no lambdas; comments say what, then why.**
Plain English: a block worth explaining is worth a name.
Ask: hoist into `substituteElementOfCompositeType`, `coerceOperandsOfBuiltinBinaryExpr`, `emitStringLitAsConstantArray`.
- "no lambda, move it into standalone function with proper commenting to document what the function is doing." [785] PR 11533
- "The description should state what the function is doing, follow by a simple summary of why we need this function if its intention isn't obvious" [764] PR 11493
- "not valid comment. Should explain in complete english setence with examples:" [771] PR 11493
Same as Tess R3, R5 and R10.

**Y29. Names carry no qualifier the code is not specific to.**
Plain English: a generic helper does not mention the feature that first needed it.
Ask: drop `WorkGraph`, `Abort`, `shader` and `pack` from names of general helpers.
- "the check here is nothing specific to WorkGraph, why does the function name has WorkGraph in it?" [714] PR 11437
- "there is nothing about this functionality that is specific to "shader", so why put shader in the name?" [790] PR 11542
- "again this func has nothing to do with pack. should named `areIntValsSemanticallyEqual`." [835] PR 11571
Same as Tess R7.

**Y30. Delete redundant checks and dead branches now; leave dead values to DCE.**
Plain English: once a stage guarantees something, the later check is noise; the cleanup pass removes leftovers.
Ask: remove the branch the parser made unreachable; do not hand-remove a leaked instruction.
- "namespace decl can never nest inside a generic so this branch is not necessary." [810] PR 11534
- "it is ok to leave it for the dce pass to clean up." [266] PR 10098
- "`stage == Stage::Node` is redundant with the `if (stage != Stage::Node)` check inside `isThreadLaunchNode`" [716] PR 11437
Same as Tess R12 (delete dead code).

**Y31. Mark exposure: `internal` for library-only declarations, `experimental` modules for unstable features, no enum cases that admit invalid code.**
Plain English: say who may use a thing, and keep unfinished things behind an explicit opt-in.
Ask: `internal` on core-module helpers; `import experimental.workgraph`; remove the `None` case.
- "mark it as `internal` if not supposed to be called outside core library." [240] PR 9926
- "This communicates very clearly that workgraphs are experimental, and is subject to future change/removal." [538] PR 10878
- "why do we need the `None` case? This will allow user to write invalid code." [346] PR 10076
Yong only.

**Y32. Explain the change; a PR a reviewer cannot understand does not land.**
Plain English: say which instruction failed, what its operands were, and why the fix is right.
Ask: rewrite the description; add a benchmark for a performance PR; answer "why" before merging.
- "we should stop letting agents creating PRs with bad descriptions like this that makes it impossible to review." [736] PR 11491
- "Which instruction is triggering the assert? What are its operands?" [185] PR 9300
- "Also, update PR description with a benchmark showing detailed perf improvements." [783] PR 11517
Same as Tess R6 and R17.

**Y33. Stay focused; preexisting problems and broad cleanups go to a follow-up.**
Plain English: fix what the PR is about, file the rest.
Ask: a separate branch for the `_Texture` refactor; an issue for every disabled test.
- "For this PR, it is probably fine to stay focused and not worry about this preexisting problem." [552] PR 10981
- "The disabled tests should have an issue number attached to it." [648] PR 11217
- "Let's do autodiff support in a follow up." [858] PR 11571
Same as Tess R15.

**Y34. Flat code: early returns reduce nesting; big `if` bodies become functions; bundle threaded parameters.**
Plain English: the main path reads straight down.
Ask: `if(!entryPoints) continue;`; an `InheritanceInfoContext` struct; a lazy `LookupChainIterator`.
- "coding style: too many nested levels here. Use early returns to reduce nesting." [380] PR 10046
- "The `if` below has a very big body that make sense to live in its own function." [693] PR 11368
- "Wonder if it is time to clean this up into a `InheritanceInfoContext` that wraps both these parameters." [692] PR 11368
Same as Tess R14 and R9.

**Y35. IR lowering is target-neutral; target-dependent work lives in target legalization or target rule classes.**
Plain English: a module is lowered once and can be emitted for any target later, so lowering must not peek at the target.
Ask: add SPIR-V debug line info in SPIR-V legalization; put SPIR-V layout rules in the SPIR-V rule class.
- "I don't think it is correct the change the IR lowering logic and have it depend on the current compilation target." [3101] PR 9371
- "This logic doesn't belong to `DefaultLayoutRulesImpl`, and should be in layout rule types that correspond to SPIRV/GLSL." [3095] PR 8383
- "In the frontend, things should be named in a platform agnostic way. So we should prefer `bindlessSpaceIndex` here." [3183] PR 9870
Same as Tess R21.

**Y36. One opcode per concept, one canonical syntax, and a stable id for every new opcode.**
Plain English: two spellings of the same thing map to one IR node; the stable-names table gets the new entry.
Ask: merge `[noinline]` and `[NoInline]` into one `IRNoInlineDecoration`; canonical Slang writes `.` not `::` or `->`.
- "There is no point having duplicate IR opcodes." [3163] PR 9735
- "you need to update slang-ir-insts-stable-names.lua to register the new NoInlineDecoration opcode with a stable opcode value." [3144] PR 9735
- "Canonoical slang code should always use `.` everywhere." [3118] PR 9560
Same as Tess R12 and R23.

**Y37. Avoid shader-only and C++-appeasement words; Slang covers kernels and host code.**
Plain English: say program, kernel or code rather than shader; do not document `::`, `->` or `const T*` as Slang.
Ask: rename "shader" terms in the reference; drop `::` from docs; say `const` pointers are not allowed.
- "Avoid the shader term. Cuda kernels are not shaders, host executables are not shaders." [3173] PR 9732
- "let's not mention anything we added to the language that are just to appeal c++ users in the reference." [3119] PR 9560
- "Opaque type is not an accurate term for all the special types we have to deal with." [3174] PR 9732
Same as Tess R20.

**Y38. A global behavior change waits until CI covers it.**
Plain English: do not change what `-O0` means before every CI test runs at `-O0`.
Ask: hold the PR; add the CI configuration first.
- "Before we try to do anything that changes `-O0` behavior, we need to have all our CI tests run with `-O0` first." [3105] PR 9369
- "let's not rush to do this. `-minimum-slang-optmizations` is not well tested and users are advised to use it at their own risk." [3104] PR 9369
Yong only.

### Yong's process habits

- He drives bots by mention and expects authors to answer AI review comments. "@copilot please address the comments." [278] PR 10121; "also can you respond to the AI generated comments?" [391] PR 10638
- Failing tests go on the expected-failure list with a tracking issue. "we can add it to the expected failure list for now, and make sure we track all failing tests in an issue." [219] PR 9880
- A sudden CI failure needs a root cause. "Question is why is CI suddently failing when nothing was broken when the PR got checked in. What changed?" [855] PR 11584
- Language changes update the user guide and reference. "have we updated our user guide and language reference docs to reflect this change?" [907] PR 12151
- Spec proposals cover the core language, not library intrinsics. "Our language spec currently do not cover standard library so it doesn't feel to me that every new intrinsic needs to go through language process." [787] PR 11488
- He reverses himself when shown evidence. "So I am fine with the original TupleType approach now." [844] PR 11542
- On his own PRs, most replies are agent-written close-outs with a commit hash. "Fixed in c4f111cce. The frontend concat diagnostics now only fire when the non-axis dimensions are provably different, and the symbolic-axis path now uses a potential-axis check so unresolved symbolic dims defer to late specialization instead of failing early." [395] PR 10645
## (d) What the older year adds

The older year is 2024-11-05 to 2025-11-04: 366 Tess comments and 713 Yong comments. Most of it confirms the recent-year rules with earlier quotes. This part lists only what the older year adds or changes, so that a reader can tell dated findings from current ones.

### Terms and corrections that appear only in the older year

Several of these name things that were later renamed, so they are evidence of history, not of current usage.

| # | Finding | Quote (≤ 25 words) | PR | idx | Status today |
| --- | --- | --- | --- | --- | --- |
| O1 | `Bindless<T>` is a dedicated type, not pointer syntax (Yong) | "I don’t like the idea of using pointer syntax for this because it is a much more limited version of pointers" | 6002 | [2548] | Renamed `DescriptorHandle<T>`; the rule survives. |
| O2 | `#feature` flags → `#language slang 2025.1 stable/experimental` (Yong) | "supporting individual feature flags can lead to fragmentation of possible compiler modes" | 5563 | [2534] | Became `#language`; "fragmentation" is older-year vocabulary. |
| O3 | `#version` → `#language` or `#lang` (Yong) | "Done, now allows #language or #lang instead of #version." | 7230 | [2592] | Tess later preferred `#language` over `#lang` [1900]. |
| O4 | Diagnostics defined in `slang-diagnostic-defs.h` (Yong) | "it is probably better the define the diagnostics in `slang\slang-diagnostic-defs.h` similar to" | 8844 | [181] | Definitions now live in `slang-diagnostics.lua`. |
| O5 | "bitdata" types, coined for layout-identical types (Tess) | "Slang eventually needs to have a notion of "bitdata" types (for lack of a better term)" | 6028 | [3231] | Not adopted; "ordinary type" is her current word. |
| O6 | "programmer error", deliberately not "undefined behavior" (Tess) | "it is programmer error (I'm going to hold back from saying "undefined behavior")" | 6002 | [3215] | In 2026 she asked for "undefined behavior" in a different context [2372]. |
| O7 | "nul" terminator considered, then dropped (Tess) | "I was going to be pedantic and request that we refer to it as a "nul" terminator" | 7496 | [1019] | Not pursued. |
| O8 | File-internal functions `static` with a `_` prefix (Tess) | "functions that are internal to an implementation file like this should be declared `static` and have their names start with an underscore prefix" | 7496 | [1035] | Withdrawn in the same PR when the function gained other callers. |
| O9 | Backticks instead of single quotes to quote code in diagnostics (Tess) | "use Markdown-style formatting (and thus backticks for quoting code) instead of the current convention (single quotes used to quote code)" | 7229 | [978] | A proposal; the single-quote convention still stands. |
| O10 | HLSL hit objects via `__intrinsic_asm ".Invoke"` rather than NVAPI (Yong) | "we should implement this with `__intrinsic_asm ".Invoke";` for HLSL target." | 7763 | [78] | NVAPI hit objects were later re-gated behind an opt-in. |
| O11 | `./buildDebug/bin/slang-test` as the test path (Yong) | "`./buildDebug/bin/slang-test tests/path/to/test_file.slang`" | 7673 | [2651] | Builds now land in `build/Debug/bin`. |
| O12 | `StringLiteral` is reserved by the type system; the new type is `ShortString` (Yong) | "`StringLiteral` is a term that has special meaning in the type system context, and I prefer we don't use it here." | 7496 | [21] | Tess doubted the `Short`/`Small` prefix [1056]. |
| O13 | `bfloat16` → `bfloat16_t` for consistency with sized types (Yong) | "should this be `bfloat16_t` to stay consistent with other explicitly sized types like `int64_t`?" | 7078 | [7] | Tess prefers `UInt8`-style names for builtin types [1117]; the two conventions coexist. |
| O14 | "casting" (explicit) versus "conversion" (implicit) (Tess) | "I try to distinguish (explicit) casting from (implicit) conversion of types" | 6028 | [3227] | Still her usage; no glossary entry yet. |
| O15 | "combined texture-sampler pair" (Tess) | "When possible, I tend to refer to such things as "combined texture-sampler pairs."" | 6028 | [3235] | Candidate language-glossary term. |
| O16 | "size in bytes", never "length" or "byte count", for strings and buffers (Tess) | "buffers have *sizes* not *counts*." | 7496 | [1013] | Candidate convention: index/count for elements, offset/size for bytes. |
| O17 | No "characters" in Slang strings; bytes or Unicode scalar values (Tess) | "I would rather Slang not go down the road of conflating the Unicode scalar values in a string with "characters."" | 7496 | [1010] | Wants a distinct `Byte` type [1015]. |
| O18 | "integer", not "integral"; "8-bit" singular (Tess) | "The term "integral" has too much overlap with its definition in the integral calculus, and will confuse many readers." | 7496 | [1038] | Convention. |
| O19 | export/import, not `Extern`, for linkage (Tess) | "The majority of the Slang codebase already uses the export/import terminology" | 7447 | [1064] | Matches Yong's public-vs-export rule [916]. |
| O20 | `some IFoo` is not a "thin-wrapper type" (Tess) | "I think it is inappropriate to refer to a `some` type as a "thin-wrapper type," because they are fundamentally *not* wrapper types at all." | 7229 | [970] | `some` types: a specific but unknown concrete type. |
| O21 | A bare interface is a "non-proper type" made proper by context (Tess) | "just plain `IFoo` is a non-proper type that only gets *made* proper in a given context" | 7229 | [974] | The root of the 2026 "proper type" rule. |
| O22 | "associated type", not "associatedType", in diagnostics (Tess) | "we should say "associated type" and not "associatedType"" | 7229 | [977] | Words over code in messages. |
| O23 | `SpirVDExportDecoration` → `SPIRVExportDecoration` (Tess) | "Naming conventions: change `SpirVDExportDecoration` to `SPIRVExportDecoration`." | 7447 | [1058] | Same acronym rule as [1159]. |
| O24 | `int` for all counts and indices; no unsigned (Yong) | "The convention in Slang is to use `int` for all size/count values. We don't use unsigned ints." | 7496 | [154] | Convention not seen in the recent year. |
| O25 | `[SPIRVExport]` as a separate attribute instead of overloading `export` (Yong) | "it is probably safer for now to introduce a separate attribute for it, e.g. `[SPIRVExport]` for the purpose." | 7447 | [32] | Same public-vs-export distinction. |
| O26 | 0 means success, for COM compatibility (Yong) | "We want to reserve 0 for success so that it works with COM interface convention." | 6916 | [2575] | API convention. |
| O27 | `do {} catch {}` rather than `try {} catch` (Yong) | "I am leaning towards that we just support `do{}catch(){}` syntax for simplicity of the lowering logic." | 6916 | [2587] | Error-handling syntax decision. |
| O28 | `#version` → `#language`: the directive names the language, not a version (Tess) | "be `#language`. That name more clearly articulates what the directive is actually specifying" | 7230 | [3276] | Adopted. |
| O29 | base/leaf IR classes → abstract/concrete (Tess) | "eliminate the base/leaf framework for classifying them and instead think of them in terms of abstract and concrete types in the hierarchy." | 7559 | [3302] | Adopted in the fiddle-generated IR definitions. |
| O30 | "pending layout" wrapper removed; `SimpleLegalVarChain` → `LegalVarChain` (Tess) | "we can simply rename `SimpleLegalVarChain` to `LegalVarChain` and get rid of this wrapper type entirely." | 8762 | [3442] | Feature removed; the term is history. |
| O31 | `cref`: an explicit by-reference immutable borrow (Tess) | "The notion of `cref` would be an explicit by-reference immutable borrow" | 7971 | [3347] | Became `borrow`; `__constref` is the legacy alias [1486]. |
| O32 | `__constref` carried two meanings, read-only `__ref` and read-only `inout` (Tess) | "we still have to deal with the overloaded meaning of `__constref` soon." | 8427 | [3363] | Split in PR 8592 into `RefParamType` and `BorrowInOutParamType`. |
| O33 | `__ref` is a "true by-reference parameter"; `inout` is a mutable borrow (Tess) | "A `RefParamType` (using the internal-use-only `__ref` modifier) is a “true by-reference parameter”" | 8592 | [3429] | The distinction behind the 2026 passing-mode glossary. |
| O34 | "immutable" = "read-only" plus "exclusive" (Tess) | "Under this model, "immutable" is basically equivalent to "read-only" plus "exclusive."" | 8526 | [3394] | Yong restated it in 2026: Immutable is an optimizer contract [3198]. |
| O35 | "unit type" for `void` inside the compiler (Tess) | "we consistently use the term "unit type" to refer to the canonical type with only a single instance" | 8708 | [3432] | In 2026 she preferred "void" over "unit" in a predicate name [1409]. |
| O36 | "pointee" type, not "target" type, of a pointer (Tess) | "every bit of information about the pointer type other than the target/"pointee" type gets lost in the first step." | 7678 | [3323] | Avoids the compilation-target collision, like "subject" [1546]. |
| O37 | "similar" or "C-like" layout, never "compatible" (Tess) | "I’m using terms like “similar” and “C-like” rather than daring to say “compatible,”" | 8249 | [3350] | Convention for layout-mode names. |
| O38 | `const` → `let` in diagnostic advice (Tess) | "We really shouldn't be encouraging people to use `const` at all, even in the latter case (where they want an immutable pointer)." | 7848 | [3355] | Same stance as R41. |
| O39 | `Poison` (undefined address) vs `LoadFromUninitializedMemory` (undefined contents) (Tess) | "the `LoadFromUninitializedMemory` case is strictly for the case where the *address* refers to a valid memory location, but the *contents* are uninitialized" | 8708 | [3433] | IR vocabulary. |
| O40 | IR mnemonics are lowerCamelCase, derived from the UpperCamelCase key (Tess) | "the mnemonic should really be `rwStructuredBufferLoad`." | 7559 | [3303] | Fiddle convention. |
| O41 | `setInsertBefore()` on a param → an explicit, unambiguous name (Tess) | "rename the operation to something like `setInsertBeforeExactInstEvenIfItIsAParam()` or something more pleasant but equally unambiguous." | 8526 | [3377] | Same rule as R7. |
| O42 | `AddressSpace::UserPointer` checks → `asExplicitPtrType()` (Tess) | "make it easier to catch cases that are currently using the `AddressSpace::UserPointer` thing to check for explicit pointers from the user's program." | 8526 | [3385] | Precursor of the 2026 pointer-opcode rule [2495]. |
| O43 | "take pointer" → "take address" (Yong) | "take address, not take pointer." | 7848 | [2826] | Still his usage in 2026 [3190]. |
| O44 | Natural layout should be made C/C++-consistent (Yong), versus C-like layout only on request (Tess) | "we should fix that layout to make it consistent with C/C++, instead of adding another layout here." | 8136 | [2836] | A recorded disagreement: "I had a long discussion with @tangent-vector and we did not reach agreement" [2838] PR 8249. |
| O45 | `Texture_Read`, `Buffer_ReadWrite` → `SampledImage`, `StorageBuffer`, `UniformTexelBuffer` (Yong) | "e.g. just `SampledImage` instead of `Texture_Read`. and `Buffer_ReadWrite` should be named `StorageBuffer` to be more accurate." | 8252 | [2865] | Descriptor kinds carry Vulkan names. |
| O46 | "smallCamel" is his word for lowerCamelCase; reflection C API uses it (Yong) | "should be `spReflectionDecl_findModifier()`" | 8308 | [2859] | Convention. |
| O47 | C-API shape: `slang_` prefix, `SlangResult`, out-parameter last (Yong) | "The API should be `SlangResult slang_createBlob(const void* data, size_t size, ISlangBlob** outBlob);`" | 8179 | [2837] | Convention. |
| O48 | No `m_` prefixes in Slang-language module code (Yong) | "I don't think we should be doing `m_` prefixes. Just name member variables directly, i.e. `handle`." | 8602 | [3055] | Applies to `.slang` library code, not the C++ compiler. |
| O49 | `IntPtr` is an integer, so `CastPtrToInt` does not apply (Yong) | "IntPtr is an int, not a ptr, so you can't use CastPtrToInt on it." | 7843 | [2716] | IR vocabulary. |
| O50 | `ElementExtract` reads an SSA register; `GetElementAddress` reads through a pointer (Yong) | "ElementExtract is sup[posed to extract a field from an SSA register, and not to read a field from a pointer." | 8340 | [2874] | IR vocabulary. |
| O51 | Updating test expectations is not a "breaking change" (Yong) | "I don't think this is called "breaking change". You just need to update any affected tests' expected result after making the change." | 7862 | [2740] | Label vocabulary. |
| O52 | `isKernelTarget`: kernel target versus host target (Yong) | "I think it is more appropriate to name this `isKernelTarget`." | 8686 | [3026] | Candidate compiler term. |
| O53 | Test file names are all lower case (Yong) | "file names should be all lower case." | 8259 | [2846] | Convention. |
| O54 | `eval` → `load` when the operation loads (Yong) | "is it just loading from the address? if so why isn't it called "load"?" | 8602 | [2981] | Same rule as R7. |

### Rules seen only in the older year

#### Tess

- **R35. Sizes and offsets are bytes; counts and indices are elements.** "We should strive to be correct about when we use index/count and when we use offset/size terminology." [1018] PR 7496; "strings should, in general, only report their *size* in bytes (for UTF-8)" [1010] PR 7496
- **R36. Every test carries a comment saying what it tests, for a developer years later.** "I would like for test cases to include a comment detailing *what* they are testing." [1068] PR 7447; "imagine a developer 1-2 years from now who is working on the compiler and finds that this test is failing" [1068] PR 7447
- **R37. New keywords go through the syntax-declaration machinery, never lookahead string tests.** "Would be great to at least *try* to register `some` as a syntax declaration." [985] PR 7229; "new syntax to be added via these mechanisms rather than via ad-hoc testing for a specific string in the lookahead" [986] PR 7229
- **R38. Type-level features live on types and type expressions, not on variables or decorations.** "Putting so much of the logic related to a feature for *types* on compiler code related to *variables* worries me a lot." [988] PR 7229; "I'm a little concerned about yet again encoding the relevant information on variables instead of at the level of the types themselves." [981] PR 7229
- **R39. Reflection comes from the AST and `.slang-module`, never from the IR.** "The translation from a Slang AST down to Slang IR is a lossy transformation." [1070] PR 8209; "Keeping the scope of what Slang IR needs to be good for narrow helps us to avoid creeping complexity/scope" [1070] PR 8209
- **R40. Diagnostics are full English sentences with no trailing period, words over code.** "There shouldn't be any trailing `.` punctuation" [977] PR 7229; "we should lean toward *not* writing things as code and instead use words." [977] PR 7229
- **R41. No `const` on Slang parameters in tests or examples; it is an anti-pattern.** "Please do *not* put `const` here. This is a stylistic anti-pattern in Slang code" [1053] PR 7496
- **R42. Never mutate a declaration's type after creation; never create declarations while querying a type.** "I'm not a fan of logic that *changes* the type of a declaration after that declaration has already been given a type." [953] PR 7229; "there is *no* circumstance in which querying the type of a variable should *ever* be creating new declarations via the `ASTBuilder`." [987] PR 7229
- **R43. Core-module overloads are generics over constrained parameters, never interface-typed parameters.** "Writing these as generics is the Right Way to express this" [990] PR 7428; "Otherwise it would risk getting compiled to use dynamic dispatch." [989] PR 7428

- **R44. A stale or copy-pasted comment is a defect, not a nit.** "This copy-pasted comment doesn't apply to this new type of expression." [3354] PR 7848; "Nitpick: comment hasn't been updated." [3324] PR 7764
- **R45. Flags that will combine are bitmasks of single-bit members.** "making sure that this `enum` can be treated like a bitfield, so that there are distinct single-bit flags for `Read` and `Write`" [3322] PR 7678; "it would potentially help to have something like a bitmask of possible side-effecting behaviors that an operation might have" [3415] PR 8547
- **R46. Code generation is written as templates, never by pasting strings; generator features follow demonstrated use.** "eliminating as much of the code like this that generates C++ from Lua by pasting strings together as possible" [3436] PR 8688; "before I add too many fancy new features to fiddle we have enough use cases in the codebase to justify those features" [3290] PR 7482
- **R47. A language feature is weighed by its cost to optimization and to every user's compile time.** "the many restrictions a language like Slang has historically placed on pointer use are there for a reason." [3424] PR 8547; "means that *every* user of Slang now pays for that feature in terms of it taking more time and effort" [3424] PR 8547
- **R48. A semantic property gets its own instruction so passes cannot ignore it.** "Each of these would make the relevant semantic properties manifest in the instruction itself." [3408] PR 8526; "tied to structural properties of the Slang IR in a way that other passes can't naively/glibly ignore them" [3382] PR 8526. This is Yong's Y14 in Tess's words.
- **R49. The dangerous primitive never gets the enticing short name.** "the verbose name was there to discourage others from ever using it" [3328] PR 7798; "give them the best name we can think of (that isn't an outright lie)" [3377] PR 8526

Everything else in her older-year comments restates R1 to R34, most often R7, R12, R19, R20, R30 and R33.

#### Yong

- **Y39. A regression test must fail without the fix.** "What happens when you run the test without the code change?" [5] PR 6392; "Also the added regression test isn't reproducing any crashes at all." [75] PR 7757; "you are fixing a different issue and didn't reproduce the crash." [107] PR 7842
- **Y40. Emit stays trivial; the IR arrives as close to its final legal form as possible.** "We should keep emit logic as straightforward as possible and avoid doing complex last minute transformations." [41] PR 7620; "the Slang IR should be in a form that is as close to the final legal form as possible." [41] PR 7620
- **Y41. Solve problems in the type system before adding modifiers or attributes.** "Whenever possible, we should solve the problem with the type system instead of through new modifiers or attributes." [2576] PR 6916; "The name based checking is a big code smell, and always should be avoided." [2563] PR 6832
- **Y42. Code with no purpose does not exist; delete redundant branches.** "If it is not serving a purpose, it shouldn’t exist in our codebase." [13] PR 7229; "This branch is implemented exactly the same as the general case below, maybe just remove it" [120] PR 7854
- **Y43. Transformations use an iterative worklist and the `InstPassBase` helper; no O(n) lookups in loops.** "an example of how to write an iterative work-list based transformation pass." [2644] PR 7607; "You should use the `InstPassBase` helper class to help you visit all child insts" [89] PR 7814; "don't do consecutive calls to `findDecoration` which is O(n) over number of decorations." [2640] PR 7607
- **Y44. Generated docs are fixed at the generator, and features ship with user-guide updates.** "we need to fix the docgen logic in the compiler code instead of fixing directly the md file." [4] PR 6040; "Can you update the user guide?" [2580] PR 7131
- **Y45. Changes scoped to an experimental language version are not breaking changes.** "2026 is an experimental language version that we are actively exploring." [15] PR 7229; "It is not a breaking change if it is only effective in 2026." [15] PR 7229
- **Y46. Stable opcode ids are frozen; internal core-module attributes may change freely.** "We should never be changing existing opcodes in this file." [83] PR 7496; "Don't worry about backward compatibility at all." [64] PR 7714
- **Y47. Tests are executable with FileCheck, mixed inputs, and no `#define` tricks.** "Also you should craft this as an executable test" [70] PR 7728; "The test case should have `condition` being a mixed matrix of `true` and `false` instead of just being `true`." [2623] PR 7566; "Don't use #defines, just declare a different set of interface and impl types with comments explaining what they are testing." [2613] PR 7452

- **Y48. Memory optimizations assume mutability and aliasing; a load or store is removed only when the root address is provably immutable and nothing intervenes.** "you can only remove a load/store if you can prove it is safe to so, which means the behavior code code won’t change." [2884] PR 8433; "We should consider StructuredBuffer as mutable by default, since the resources may alias." [2929] PR 8433; "This is only correct when there are no side-effect instruction between `Load` and `GetElementPtr`." [2756] PR 8042
- **Y49. A parameter transform is driven by the parameter, never the argument's current shape; the body changes before its call sites.** "we transform the arg is not determined by the type of the argument, but solely by whether or not the parameter type is transformed." [2762] PR 8042; "we should always be updating the function body before updating its callsite." [2766] PR 8042
- **Y50. FileCheck over `.expected` files; match only the important lines; `CHECK-DAG` when order is irrelevant.** "Match only important lines, not every line." [2741] PR 7862; "Use filecheck instead of.expected file to verify results." [2744] PR 7984; "should be //CHECK-DAG: to make these checks order independent." [2701] PR 7837
- **Y51. Types and witnesses are hoistable; let `IRBuilder` place them, never hand-manage scope.** "We should just make whatever IR inst that reprents "this_witness" a hoistable inst and let the ir builder automatically determine the scope." [2891] PR 8467; "That can't be true, because types are automatically hoisted to global scope." [2719] PR 7939
- **Y52. New warnings stay silent in Slang 2026 mode, and legacy code keeps legacy behavior.** "We need to make sure no warnings are generated in Slang 2026 language mode." [2736] PR 7984; "There are some legacy Falcor code depending on the broken behavior right now, so we can't just enable it globally for the legacy language version," [3065] PR 8839
- **Y53. Support a feature robustly or not at all: generic callers, recursion, nested and aggregate shapes.** "then we need to support it robustly, whether or not being approached from a direct call or from a generic function." [2986] PR 8599; "While we don't support recursion today, I want to make this pass robust against recursion." [2780] PR 8042; "What if it returns a `struct` that contains resource typed fields?" [2926] PR 8434
- **Y54. Minimal public surface; experimental APIs carry a notice; performance PRs ship numbers.** "We should not expose this full struct to the user. For now this should just have one entry: Device." [2765] PR 7848; "put a big notice here that this is under active design and experiment and we may remove or change any or all parts of it" [2980] PR 8602; "Can you please include some concrete performance numbers with nontrivial performance optimization PRs like this?" [2966] PR 8552

His older-year verdict vocabulary is binary: "This is a wrong fix." [75] PR 7757; "wrong fix, closing." [173] PR 8257; "The change here is a bandaid instead of a fix of the root cause." [172] PR 8429. When CI cannot run the hardware he asks for a plan: "what's the testing plan?" [2897] PR 8469.

### What the older year confirms

- Tess's early-out, naming and comment rules are already fully formed in 2024, with the same words: "Delete this comment; it serves no purpose." [1001] PR 7797; "write comments that focus more on the problem the code is trying to solve, *how* it will go about doing that" [1061] PR 7447
- Yong's producer rule predates the agent era: "This is putting a band aid to a problem that has deeper roots." [69] PR 7728; "This is pushing the failure to further down the pipeline." [2628] PR 7597
- Both already treated proposals as the gate for language changes: "A large-scale language change like this really ought to start with a fleshed-out feature proposal" [1011] PR 7496; "We shouldn't be adding implementation like this without doing a proper language proposal" [145] PR 7945
- Both already drove bots by mention and judged them on time cost: "This PR is a time loss to use copilot." [128] PR 7854; "@claude make the remaining changes that were requested during review" [1008] PR 7797
## Files next to this document

- `github-comments.jsonl`: one line per comment by either author on the 762 fetched PRs. Fields: author, pr, kind, path, line, created_at, body, idx, range, is_reply, state, url.
- `github-stats.json`: comments per author, range and kind; PRs searched and covered; medians; own-PR and bot-PR splits; API-call totals.
- `github-terms.json`: the candidate glossary changes in the shape of `../experts-terms.json`.
- `github-term-counts.json`: regex term counts per author, with older-year counts.
- `tess-authored-prs.jsonl`, `tess-authored-vocab.md`, `tess-authored-principles.md`: Tess's 67 authored PR descriptions, their Concepts and Vocabulary sections, and their principle sentences.
- `tess-gh.txt`, `tess-gh-older.txt`, `yong-gh.txt`, `yong-gh-older.txt`, `yong-gh-recent-ext.txt`: the comment dumps, indexed `[n]`; `tess-gh-cues.txt`, `tess-gh-rules.txt`, `tess-gh-replies.txt` are the recent-year subsets the readers used.
- `reports/*.md`: the fourteen reader reports; `verify.py` confirmed every quote in them and in this document against the JSONL.
- `raw/`: the search results and per-PR API responses; `raw/api-calls.log` lists every successful call.
- `fetch.sh`, `process.py`, `analyze.py`, `build_tables.py`, `terms_data.py`, `verify.py`, `check_sentences.py`, `extract_report.py`, `BRIEF.md`, `BRIEF-older.md`: the scripts and reader briefs.
