https://addyosmani.com/blog/self-improving-agents/


**Imagine ending your workday and waking up to new features coded, tested, and ready for review.** This is the promise of autonomous AI coding agents - harnessing tools like **Claude Code** in continuous loops to improve and ship code while you sleep.

In this write-up, I’ll cover how to set up these self-improving agent loops - from orchestrating the loops and structuring context files to memory persistence, QA validation, scaling, debugging, and risk management. Hopefully something in here will be helpful to others.

***This write-up compliments Ryan Carson’s excellent [How to make your agent learn and ship while you sleep](https://x.com/ryancarson/status/2016520542723924279) which I highly recommend reading.*** We recently had some excellent chats over dinner about the future of agentic coding and I wanted to expand on some of the techniques he outlined.

## The “continuous coding loop” (Ralph Wiggum technique)

At the heart of this approach is an iterative **agent loop** often nicknamed the “Ralph Wiggum” technique (popularized by Geoffrey Huntley and folks like Ryan Carson). The key idea is you break development into many small tasks and run an AI agent in a loop to tackle them one by one.

Each iteration of the loop follows a **cycle**

1. **Pick the next task** from a to-do list (e.g. [a JSON of tasks](https://github.com/snarktank/compound-product#:~:text=Each%20iteration%20of%20the%20loop%3A)) that isn’t done yet.
2. **Implement the task** - the agent writes or modifies code for that specific feature/fix.
3. **Validate the change** - run tests, type checks, or other quality checks for that task.
4. **Commit the code** if checks pass, integrating the change into the codebase.
5. **Update task status** (mark it as done) and log any learnings.
6. **Reset the agent context** and repeat for the next task, until all tasks are complete or a stopping condition is met.

By resetting its memory each iteration, the agent [avoids accumulating confusion](https://www.aifire.co/p/automated-coding-build-apps-while-you-sleep-using-ai-agent#:~:text=This%20approach%20solves%20the%20common,both%20founders%20and%20experienced%20developers) from prior tasks and stays focused. This “stateless but iterative” design is key to reliability - it **solves the context overflow problem** that plagues asking an AI to build a whole feature in one go.

Instead of one enormous prompt that can cause the model to drift or forget details, the agent is repeatedly given a fresh, bounded prompt for a single well-defined task.

The result is cleaner code and fewer hallucinations because each run starts with a clear slate and explicit instructions.

Here an agent continuously picks tasks, writes code, runs tests, and updates the task list until all tasks pass.

### Small tasks with clear criteria

Breaking work into **atomic user stories** or tasks is important. Each task should be **small enough to fit in one AI session** and have unambiguous pass/fail criteria.

For example, instead of “Build the entire dashboard” you’d have tasks like “Add a navigation bar with links to Home, About, Contact” with acceptance criteria specifying exact expectations (e.g. “the current page link is highlighted in blue”).

This granular way makes sure the agent knows what “done” looks like for each step. It also reduces the chance of the agent going off-track like if a task fails its tests or criteria, the loop can catch it immediately and correct course.

*Implementation tip:***Define a SPEC and convert it to tasks JSON.** Start by writing a clear specification for the feature, possibly with the help of an AI to flesh out edge cases.

Then translate that into a structured task list (e.g. a prd.json file) containing all the small user stories and acceptance criteria. Tools like Carson’s [**/prd and /tasks skills**](https://github.com/snarktank/compound-product#:~:text=Two%20skills%20are%20included%20for,PRD%20creation%20and%20task%20generation) for Amp/Claude can [automate this conversion](https://github.com/snarktank/compound-product#:~:text=Key%20features%3A).

The result is a machine-readable to-do list that your agent loop will execute step by step.

### Orchestrating the loop

Running the loop can be done via a simple script. In [Carson’s implementation](https://github.com/snarktank/ralph), this is [literally like a Bash script](https://ghuntley.com/ralph/#:~:text=If%20you%27ve%20seen%20my%20socials,Ralph%20is%20a%20Bash%20loop) or Python script (e.g. ralph.sh) that repeatedly invokes the AI agent with a prompt template. With Amp or Claude Code, you might use their CLI commands or a plugin to achieve the same effect. For example, using Amp’s CLI, one could run a pseudo-code loop like:

```bash
while :; do
   amp run \-s prompt.md \-o progress.txt  \# Run Amp with the prompt, save output
   if grep \-q "\<promise\>COMPLETE\</promise\>" progress.txt; then break; fi
done
```

In practice, the loop script will load the task list, pick the next unfinished task, format a prompt (including context like relevant code files and guidelines), and call the AI model. When the model’s response indicates success or failure, the script handles applying code changes and running tests. This repeats until all tasks are completed or a max iteration limit is hit.

The key is that each iteration is isolated - the agent is **spawned fresh each time**, often as a new Claude or GPT process, so you truly wipe the slate clean but feed it the necessary context anew each time.

**Compound loops:** Beyond a single sequence of tasks, advanced workflows orchestrate multiple phases of loops.

[**Compound Product**](https://github.com/snarktank/compound-product#:~:text=A%20self,priority%2C%20and%20autonomously%20implements%20it), for example, is an open-source system that first runs an **Analysis loop** (an AI reading daily reports to identify what to build), then a **Planning loop** (to generate a PRD and tasks), and finally an **Execution loop** (the coding agent that implements the tasks). This compound pipeline means the agent not only codes features but also decides what the highest priority feature *is*.

While not every project needs this level of automation, it showcases how loops can be chained: one agent’s output (e.g. a list of tasks or a branch name) becomes another agent’s input in a larger continuous delivery system.

## Best practices for context and memory: The AGENTS.md handbook

One of the most powerful mechanisms in these agent loops is the use of persistent **context files** that carry knowledge forward between iterations.

Rather than trying to “stretch” a single AI session to remember everything (which is impossible beyond the context window), we explicitly write important information to disk so it can be *re-injected* in future prompts. The primary file for this is commonly named **AGENTS.md** (though some use [MEMORY.md](https://ericmjl.github.io/blog/2025/11/8/safe-ways-to-let-your-coding-agent-work-autonomously/#:~:text=When%20you%20catch%20an%20agent,An%20example%20prompt) or similar).

**What is AGENTS.md?** It’s essentially a running notebook of the agent’s discoveries, the project’s conventions, and any guidance you want all future agents to know.

After each task, the loop can append key learnings: for example, “Note: The codebase uses Library X for Y, so follow that pattern” or “Gotcha: Whenever updating the user model, also update the audit log”.

Over time this becomes a treasure trove of hints that steers the agent away from repeating past mistakes. In Carson’s Compound Product philosophy, [*“agents update AGENTS.md - discovered patterns are documented for future iterations”*](https://github.com/snarktank/compound-product#:~:text=Compound%20Product%20is%20based%20on,should%20make%20future%20improvements%20easier). This means each improvement literally makes future improvements easier, because the agent accumulates a knowledge base of what the codebase looks like and how to work with it.

**Structuring the knowledge base:** Organize AGENTS.md into sections so it’s easily readable by both humans and AI. For example:

- **Patterns & Conventions:** High-level patterns (e.g. “This project uses SSR, UI components live in /components, API in /routes”).
- **Gotchas:** Things that have tripped the agent or developers up (“When adding a new enum, update the constants.ts file or tests will fail”).
- **Style/Preferences:** Coding style notes (“Follow ESLint rules as configured; prefer functional components over classes”, “Use pytest fixtures for tests as in existing tests”).
- **Recent Learnings/Changes:** Summaries of recent issues and how they were resolved.

Keep entries brief and factual - they should serve as **prompt additives** that guide the model. Many AI coding tools (Claude Code, Cursor, Amp) will [automatically include certain files](https://github.com/snarktank/ralph#:~:text=After%20each%20iteration%2C%20Ralph%20updates,discovered%20patterns%2C%20gotchas%2C%20and%20conventions) like AGENTS.md or README.md in the prompt context if they’re present. For instance, when an agent starts on a new iteration, Amp will scan the repo and pull in AGENTS.md content to give the model context about the project.

**Context injection strategy:** Be mindful of context size. As your knowledge file grows, you may not always want to inject all of it for every single task (context bloat can reduce performance or cause the model to ignore instructions).

A good practice is to keep AGENTS.md focused and up-to-date, archiving obsolete info to another file if needed. Some advanced setups use retrieval: e.g., split AGENTS.md into multiple topical files and only include the sections relevant to the current task. But a simpler approach is often sufficient - keep the file pruned to the most relevant tips and let it grow gradually with the project.

**Example usage:** Suppose an agent tried to use an outdated API and you caught it.

You might stop the loop and add a note in AGENTS.md like:

*“The v1/users endpoint is deprecated; use v2/users instead.”*

Next time the agent tackles a related task, it will see this note and avoid the deprecated API. In fact, you can instruct the agent to do this itself:

*“No, don’t use the old endpoint. Instead, use the new v2/users API. Record this in AGENTS.md, then continue.”*

This [real-time feedback technique](https://ericmjl.github.io/blog/2025/11/8/safe-ways-to-let-your-coding-agent-work-autonomously/#:~:text=Correct%20agent%20behavior%20in%20real) was highlighted by developer Eric J. Ma as a way to *“create a persistent record of preferences that improves future agent behavior”*.

The agent will dutifully append the correction to AGENTS.md and carry on with the new instruction - effectively learning from the mistake.

Finally, consider sharing AGENTS.md knowledge across agents or runs. If you run multiple loops (for different projects or parallel tasks), you could centralize some common knowledge. Eric Ma’s [**MCP (Model Context Protocol) server**](https://ericmjl.github.io/blog/2025/11/8/safe-ways-to-let-your-coding-agent-work-autonomously/#:~:text=This%20approach%20creates%20a%20persistent,preferences%20across%20different%20agent%20platforms) is an example of a system to store and serve such context to different agents uniformly. In simpler terms, even a shared wiki or set of markdown files that all your agent sessions reference can ensure consistency if you have multiple autonomous agents working in tandem.

## Memory persistence and compound learning strategies

In addition to AGENTS.md, robust agent loops use several **persistence mechanisms** to retain state and avoid forgetfulness across iterations. Carson’s Ralph loop implementation uses at least [four channels of memory](https://github.com/snarktank/compound-product#:~:text=Memory%20Between%20Iterations) between runs:

- **Git Commit History:** Each iteration’s code changes are committed, so the next iteration can do a git diff or inspect the repo to see what changed. This way, the agent doesn’t need to recall previous code - it can read it from the repository. The commit messages themselves can provide context as well (“Iteration 5: Added navbar component”). Tools like Amp or Cursor allow the agent to [run git log or git diff autonomously](https://ericmjl.github.io/blog/2025/11/8/safe-ways-to-let-your-coding-agent-work-autonomously/#:~:text=Safe%20to%20auto) (with proper permissions) to gather context from version control.
- **Progress Log (progress.txt):** A plain text log appended each cycle describing what happened - e.g. which task was attempted and whether it passed or failed, along with any error messages or discoveries. This acts as a chronological memory. If the loop stops or you need to debug, you can inspect progress.txt to see where things went wrong. The agent itself can also be prompted to read progress.txt at the start of an iteration (or relevant parts of it) to remind it what was tried before. Think of it as the agent’s journal.
- **Task State (prd.json or tasks list):** The JSON file with tasks gets updated as tasks are marked done or have passes: true/false fields toggled. This file persists the *status* of each requirement. If the agent crashes and restarts, it can load prd.json and know exactly which tasks remain. The agent loop script will skip tasks that are already done and focus on the pending ones. This prevents rework and gives a sense of progress.
- **Agents’ Knowledge (AGENTS.md):** As discussed, this is the long-term semantic memory - the accumulated wisdom of past runs.

Together, these create a **compound learning loop**: the agent isn’t “online learning” in the machine learning sense, but it is *systematically recording outcomes* so that the next iteration (or the next project!) benefits from those learnings.

Every fix or pattern the agent figures out gets rolled into the context for next time. As the Compound Product README puts it, the philosophy is that [*each improvement should make future improvements easier*](https://github.com/snarktank/compound-product#:~:text=Compound%20Product%20is%20based%20on,should%20make%20future%20improvements%20easier).

Over dozens of iterations, the agent’s effectiveness can actually increase as it stops repeating mistakes and follows the conventions it has learned.

There are also **plugin-based memory extensions** you can leverage.

Claude Code, for example, supports “skills” and even marketplace plugins - you could imagine (or build) a skill that automatically saves a summary of each coding session and loads it next time. Amp’s auto-handoff feature effectively acts as a short-term memory - when the context window is about to overflow, it can hand off the conversation to a new session with a condensed summary so far. This prevents mid-task context loss and is useful for very large tasks or complex refactors.

In more experimental setups, developers have used **vector databases** to store and retrieve memory. For instance, after each iteration you could embed the diff or error messages and save the vector with a description. Before a new iteration, query the DB for similar past cases and provide that to the agent.

This can help in recognizing, say, “Oh, I’ve seen a failing test like this before and how it was fixed.” However, such approaches add complexity and may not be needed if you diligently maintain simpler artifacts (files and logs) that the agent can directly read.

**Tip:** Whatever persistence you use, periodically **verify that the agent is actually utilizing it.** A memory file only helps if it’s injected into the prompt in future runs.

Check your prompt template or agent config to ensure, for example, that AGENTS.md and recent progress.txt entries are included. In Amp and Claude, by default, files like progress.txt might not be auto-loaded, so you can modify your prompt to say: *“Here are notes from previous runs:”* and include the content.

In Carson’s setup, customizing the prompt template (e.g., prompt.md or CLAUDE.md) for your project is encouraged - you can add sections that load project-specific context or emphasize particular instructions.

## Quality assurance: Testing and validation loops

For an autonomous agent to reliably produce working code, **automated validation is paramount**. Without checks, an agent might merrily introduce bugs or failing builds while thinking it succeeded. A robust agent loop incorporates tests and other verifications as first-class citizens in the cycle:

- **Unit and Integration Tests:** Having a solid test suite dramatically improves outcomes. The agent can run npm test or pytest after implementing a task. If tests fail, the loop knows the task isn’t really done and can prompt the agent to fix the code. Ideally, every user story in prd.json has at least one test associated, either as part of acceptance criteria or in the repository’s test files. Some systems go further - e.g. instructing the agent to write a new test before coding (test-driven style) or to snapshot the app’s UI state for comparison. But at minimum, **run existing tests in each iteration**.
- **Type Checking and Linting:** Static analysis tools (type checkers like MyPy or tsc, linters like ESLint/Flake8) are great automated feedback. They catch errors quickly. These can be run as part of the loop’s quality checks before committing code. For instance, you might configure in config.json that the loop should execute npm run typecheck && npm run lint after the agent writes code, and only proceed if those exit successfully. This prevents an agent from stacking error upon error.
- **Continuous Integration (CI) in the Loop:** Some advanced setups even tie into CI pipelines. For example, Cursor’s multi-agent experiment had [a “judge” agent that could decide](https://cursor.com/blog/scaling-agents#:~:text=,planning%20itself%20parallel%20and%20recursive) if the project is complete, which might involve ensuring the GitHub Actions CI is green. In a simpler single-agent loop, you can simulate this by running build scripts or any CI checks locally as part of validation. **The loop should halt on a red flag** - if a check fails, the agent should address it (or mark the task as still failing and potentially move on if stuck after N attempts).
- **AI self-evaluation (optional):** In cases where you can’t easily write an automated test (e.g. for a UI change without a test framework), you might use the agent itself to verify. For instance, for front-end tasks, Carson’s agents use a **dev-browser skill**: the agent can spin up a headless browser, navigate to a page, and confirm that a UI element is present or an interaction works. This is essentially an agent-driven integration test. If the verification fails, the agent knows to try again. While this can be powerful, ensure you have sandboxing in place (more on safety later) since it means the agent is executing code or controlling a browser.

**Expert insight:***How do you get an AI agent to write good tests in the first place?* According to Simon Willison, the best way is to - maintain high-quality tests in your codebase, and the agent will naturally mimic those patterns. LLM-based coders tend to follow the style they see. If your repository has clear, simple tests for existing components, the agent, when asked to add a new feature, will often produce similar tests for the new code.

Willison notes that once a project has clean tests, . He also suggests : e.g. *“Use the testing style from \[some file\]”* or even instruct it to clone another repo to see certain patterns. This context seeding can drastically improve the agent’s output and reduce time spent fixing poorly written tests later.

In practice, you might not always trust an agent to create tests from scratch - many developers prefer to write or at least review tests themselves. But even then, **running those tests in the loop is essential**. It creates a feedback loop where the agent only “thinks” it is done when the code truly meets the specification (tests passing is the proxy for that). This agentic QA loop is what turns a naive “generate some code” process into a reliable engineering workflow.

## Scaling Up: Concurrent agents and multi-loop orchestration

So far, we’ve focused on one agent handling one list of tasks serially. What if you want to go faster and tackle multiple tasks or even multiple projects at once? Recent experiments in the field have tried [running dozens or hundreds of agents concurrently](https://cursor.com/blog/scaling-agents#:~:text=This%20post%20describes%20what%20we%27ve,code%20and%20trillions%20of%20tokens) on a codebase.

While this is bleeding-edge and not yet common in everyday development, it’s instructive for understanding the limits and possibilities of scaling these loops.

**Challenges of parallel agents:** If you naively run many agents on the same repo, you’ll hit issues with **coordination and conflicts**. For example, two agents might pick the same task, or one might change code that breaks what another is doing. Early attempts using [a shared file lock mechanism](https://cursor.com/blog/scaling-agents#:~:text=Our%20initial%20approach%20gave%20agents,we%20used%20a%20locking%20mechanism) revealed agents getting stuck or wasting time waiting on each other. They could also become [**risk-averse**](https://cursor.com/blog/scaling-agents#:~:text=We%20tried%20replacing%20locks%20with,there%20were%20still%20deeper%20problems), each one only making tiny safe changes and avoiding the big complex tasks - because no single agent felt “responsible” for the tough parts in a free-for-all system.

[**Planner-Worker model**](https://cursor.com/blog/scaling-agents#:~:text=)**:** A more successful pattern is to introduce hierarchy or specialization among agents. For instance, Wilson Lin at Cursor describes using **Planner agents** and **Worker agents** in a swarm. Planners are like project managers: they read the entire codebase, decide what needs to be done, and spawn tasks (even recursively creating sub-tasks). Workers then take these tasks and implement them without worrying about the broader picture.

At the end of an iteration, a Judge agent assesses if the goal (e.g. complete the project) is met. This approach prevented the aimless wandering and drastically scaled up throughput - Cursor’s team managed to have *hundreds of agents working together* on building a web browser, churning out over a million lines of code across 1,000+ files in a week.

While you likely don’t need that scale, you **can run multiple loops in parallel for different purposes**. For example, you might dedicate one agent loop to front-end tasks and another to back-end tasks simultaneously (operating on different parts of the codebase or different branches).

If you do, ensure you partition the work clearly to minimize conflicts.

Another scenario is running separate nightly loops for separate feature branches — e.g. 10 features queued up, and you fire off 10 agent processes on 10 branches. Ryan Carson predicts that [*eventually founders will be running 10+ loops like this every night*](https://x.com/ryancarson/status/2016797196222370226#:~:text=,turns%20prioritized%20reports%20into) to accelerate development. Each loop still follows the same principles, but you’ll need good CI practices to integrate all that output (just as you would with multiple human engineers working concurrently).

**Coordination tools:** If multiple agents must touch the same project, consider using coordination files or simple APIs for communication. A shared tasks.json with a locking scheme is one approach (though as noted, file locks can be tricky). Another lightweight approach is to have a “traffic cop” script that assigns tasks to agents and uses queues.

There are also emerging agent orchestration platforms that handle multi-agent workflows, but right now these are mostly custom-built or research projects rather than off-the-shelf solutions.

For most advanced users today, **scaling means iterating deeper rather than purely wider**. It’s often more fruitful to let one capable agent loop run longer (overnight or multiple days) on a complex project than to spin up a swarm that’s hard to manage. Long-running single agents are also improving as model capabilities grow.

When you entrust coding to an autonomous agent, you need visibility into its actions. Treat your agent like a real engineer whose work you’re reviewing. Here are some best practices for monitoring and debugging the agent loop:

- **Live Logs:** Keep a terminal open tailing the agent’s output or the progress.txt log in real time. The loop should print out what task it’s working on, and you should see the results of tests or any errors. If you notice the agent is looping on the same error multiple times, it might be stuck - you can intervene (stop it or give a hint). Many frameworks let you see the AI’s messages; for example, Claude Code desktop app shows the conversation thread as the agent works, and Amp’s CLI prints model outputs step by step.
- **Checkpoint Commits:** Since each iteration commits to git, you have an excellent audit trail. Use git log and git diff frequently. A quick git log --oneline -5 will show the last few commits the agent made. If something looks wrong in the diff, you can catch it before it gets too far. You can even automate a diff review - e.g., abort the loop if the diff is much larger than expected or touches critical files outside the task scope (indicative that the agent might have “gone rogue”).
- | **Inspection Commands:** Incorporate some debug commands into your loop or make them easy to run. For instance, a script to show all tasks status (jq ‘.tasks\[\] | {id, story, passes}’ prd.json) can quickly summarize progress. Checking progress.txt for the word “ERROR” or reading the last N lines can tell you why a task failed. |
	| --- | --- |
- **Agent Introspection:** You can ask the agent to explain itself if needed. For example, if it’s stuck on a task, you could modify the prompt to say “If tests are still failing after 3 tries, output your reasoning on why and a plan.” This can surface the agent’s internal chain-of-thought (so-called “self-reflection”) which might give clues. Use this judiciously - too much introspection can also confuse the loop - but it’s a tool in the debugger’s toolkit.
- **Performance Metrics:** It’s useful to log how long each iteration takes and how much cost (API tokens) it’s using. You might instrument the loop to record timing for each task and overall. If you see a particular task taking 10 times longer than others, that’s a sign it’s complex or stuck. Over many nights, you can gather stats like “features per hour” which can inform if an upgrade (model change, prompt tuning) made a difference.
- **Automated Stop Conditions:** Sometimes things go wrong - e.g., the agent gets into a futile loop (perhaps due to a tricky bug it can’t solve) or an external dependency is down making tests always fail. In addition to the normal completion condition, set up stop conditions. A simple one is a **max iterations limit** - e.g., stop after 50 loops even if not done. This prevents runaway costs and infinite loops. You can also stop on a time limit (“if this runs more than 3 hours, kill it”) or on idle conditions (“if no new commit was made in the last 5 iterations, break out”). These ensure you come back to a stalled agent rather than it running all night doing nothing useful.
- **Manual Overrides:** Even with all the autonomy, keep a human override in the loop for critical moments. A good pattern is to have the agent open a **pull request** at the end rather than merging automatically. That means you get to do a final code review each morning. You’ll likely catch anything that slipped through tests (logic issues, or something that meets the letter of acceptance criteria but not the spirit). This “human QA” step is invaluable for now - it lets you trust the agent to do the grunt work but not give up ultimate control.

If an agent consistently fails a certain kind of task, take it as feedback. Maybe your acceptance criteria are ambiguous or too strict. Or maybe the agent needs a better hint in AGENTS.md about a particular framework. Use failures as a learning signal **for yourself and for the agent**.

For example, if the agent struggles with a third-party API because it lacks context on how to use it, consider adding a brief usage example in AGENTS.md or as a comment in the code for next time. Over days and weeks, this reflective improvement (not unlike pair programming retrospectives) will make the system more robust.

## Risk management and safeguards

Running code-generating agents with commit access and shell execution rights is powerful - and risky. You must deliberately manage those risks. Here are critical areas and how to address them:

### Preventing Destructive Actions

An autonomous agent could, if misconfigured, delete files, corrupt your repo, or push insecure code. To mitigate this:

- **Limited Scope:** Run the agent on a feature branch or fork, never on main directly. This way, even if it does something crazy, your production code is untouched until review.
- **Read-Only vs Write Permissions:** Most agent platforms have confirmation gates for dangerous operations. Amp and Claude Code have flags like --dangerously-allow-all to bypass confirmations for automation.

Use these with caution. A safer approach is to [**auto-approve only read-only commands**](https://ericmjl.github.io/blog/2025/11/8/safe-ways-to-let-your-coding-agent-work-autonomously/#:~:text=Auto) and require manual approval for writes. For instance, allow the agent to run grep, git log, or npm test without asking, but do *not* allow git push or rm -rf without your explicit ok. By whitelisting safe operations, you let the agent gather info freely while containing side effects.

- **Sandboxing:** Ideally run the agent in a confined environment - e.g. a Docker container or VM - especially if it has the ability to execute code (which it often does for tests).

This limits damage from any unintended commands. Also, use API keys with minimal scope: if the agent needs an API key to, say, post a GitHub comment, give it a token that can only do that and nothing more.

- **Emergency Stop:** Always know how to kill the agent mid-run. This could be as simple as Ctrl+C in your terminal or a specific command in the agent UI (Claude Code uses Escape key to stop generation).

If you see it doing something harmful, terminate first, ask questions later. Also consider monitoring resource usage - if an agent process is consuming unusually high CPU or memory (possible if it triggers a crazy infinite loop in code), an automated monitor might kill it.

### Handling hallucinations and divergence

AI models sometimes produce outputs that are syntactically plausible but semantically wrong (**hallucinations**). In coding, this could mean calling a function that doesn’t exist, using an incorrect algorithm, or writing nonsense comments. There’s also the risk of **task divergence**: the agent might interpret a requirement incorrectly and implement the wrong thing.

Mitigations:

- **Strong Specs and Prompts:** Clear acceptance criteria and well-defined tasks are your first line of defense. If the task says “POST to /api/login and get a 200 OK”, there’s little room for the agent to hallucinate a different endpoint. Ambiguity is the enemy. Spend time up front making the tasks unambiguous and the prompt template explicit about what to do and what not to do (system prompts / preambles can enumerate “Don’t introduce any new dependencies unless specified” or “Follow the coding style used in this repository”).
- **Validation to Catch Hallucinations:** The aforementioned tests and type checks will catch many hallucinated bits (like calls to undefined functions). Type errors, reference errors, failing tests - these are signals the agent did something unreal. The loop’s logic should then prompt the agent to fix those. Often, just running the code and feeding the error output back is enough for the model to realize the mistake and correct it.
- **Periodic Refocusing:** Long-running loops can drift over time - maybe a small misunderstanding compounds. A technique to counter divergence is to **periodically restart with fresh planning**. For example, after a certain number of tasks, you might pause and re-run the /prd skill or re-scan the codebase to ensure the remaining tasks are still valid. Carson’s team notes needing *“periodic fresh starts to combat drift and tunnel vision”* in [very long agen](https://cursor.com/blog/scaling-agents#:~:text=we%27re%20nowhere%20near%20optimal,combat%20drift%20and%20tunnel%20vision) t [runs](https://cursor.com/blog/scaling-agents#:~:text=we%27re%20nowhere%20near%20optimal,combat%20drift%20and%20tunnel%20vision). Practically, this could mean stopping the agent after it completes a big chunk, reviewing the intermediate product, updating the task list if needed, and then continuing.
- **Multi-Model Cross-Check:** If available, use different models for different roles. The Cursor experiment found using a mix of models (a highly competent one for planning, a code-specialized one for coding) worked better than one model for all. You might not have multiple model options depending on your tools, but even using a second opinion model for critical steps (like running a GPT-4 check on the diff generated by Claude) can reduce errors. Some developers do this manually: e.g., after the loop finishes, ask ChatGPT to review the PR before you merge.

### Context bloat and optimization

As the project grows, the amount of context to feed the agent can become huge. If AGENTS.md and progress.txt accumulate hundreds of lines, you can’t always feed all of that into a 100k-token window. Some suggestions:

- **Summarize older content:** The agent itself can help here. You can prompt it: “Summarize the key points from the progress log above” and store that, then truncate the log. Keep summaries of summaries if necessary. This retains important info in much shorter form.
- **Divide and conquer context:** Use the task ID to only show relevant parts of logs or code. If task 7 is about the login page, you don’t need to include notes about the checkout feature in the prompt. Some automated approaches search the repository for keywords related to the task and only include those files as context.
- **Leverage training knowledge wisely:** Remember that the model has a lot of general knowledge already (about common libraries, algorithms, etc.). You don’t need to feed it documentation it likely already “knows” unless the project uses something very new or obscure. For example, you probably don’t need to paste the entire React docs; instead just note “This is a React project using Hooks and Vite” and the model can fill in the rest from its training. Lean on the model’s strengths to save context for project-specific details.

### Human oversight and continuous improvement

Lastly, treat this whole system as a living process. Monitor it, tweak it, and apply human judgment frequently. Ryan Carson, in his experience building with these loops, emphasizes the [*“elbow grease”*](https://freeplay.ai/blog/real-talk-on-building-coding-agents-a-conversation-with-amp-s-builder-in-residence-ryan-carson#:~:text=%3E%20,%28watch%20here) that goes into tuning prompts and workflow integration.

There is no one-shot fully autonomous magic. It’s more about continuous refinement.

Your role as the developer shifts from writing the code to curating the process - writing the specs, reviewing the outcomes, and guiding the AI agent at a high level (almost like an engineering manager for your AI developer team).

Keep a close eye on **costs** as well (API usage). An agent stuck in a loop could burn through tokens; set sensible limits and maybe budget alerts. In practice, though, the ROI can be huge if done right - the Ralph community has reported [massive productivity gains](https://ghuntley.com/ralph/#:~:text=,%24297%20USD.%20pic.twitter.com%2F0JgT8Q19bV), with anecdotal cases like a $50k project delivered for a few hundred dollars in API calls.

Autonomous coding agents are here, and with careful setup they can take on the grunt work of coding continuously.

With each iteration, both you and the agent get better.

Welcome to the next level of AI-augmented software engineering: ship while you sleep, and let your agents compound your progress.

*This post was formatted for better readability using Gemini*
