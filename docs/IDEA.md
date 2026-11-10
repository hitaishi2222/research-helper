A cli tool that can help in automating your research through AI.

Checkout the ../research-helper/SKILL.md , We need to make this easier for AI's to adopt and understand the path of planning and config.

## Ideas to implement (Random)

- name of cli `rh` (research-helper)
- `rh env show` -> should show the current environment set to this project
- `rh env set ...` -> should be able to change and set the all environment config (findout what are all the possibilities and give option to set them)
- `rh init` -> should create a .rh directory with all folder stuctures requied. Where all of the things should live (logs, literature, notes, plan, env-config, status etc) keeping the project space clean.
- `rh search <something>` -> should retrieve things about that topic (for eg: while reading papers `Researcher` or `Literature` agent added notes or create a paragraph in LITERATURE.md about optimization -- `rh search optimization` should give output that matches the search). No indexing needed for this. (We can check the binaries like jq,rg,fd,etc that can help while `init` and kept in env file). Use best algorithms locally to make this happen or think about struturing the files itself to make this easier.
- `rh add {note|literature|...} <HEADING/DOI>` -> should add notes with the respective heading, or literature info with DOI. If heading/doi are not present, this should create the respective heading or doi. If already present append the information to the group.
- For tasks and status purpose take inspiration from `openspec` on github. But dont follow all their spec driven task manage create a lot of files - bloating the workspace and hard to comprehend whats happening.
- `rh status` -> Should show with nice UI about the tasks running and upcomming states.
- `rh tasks` -> Should show all the tasks and subtasks done.
- `complete|working|idle|cancelled` should be the different state of a tasks (`cancelled` = a later step killed the plan). state can be changeable though cli.
- `rh workflow` should create a cli diagram where it can show the actual workflow like architecture. Check some of the cli tools that can make this possible using mermaid ex: `mmdr` or `beautiful-mermaid` check its installed or not. Its not mandatory for user to install this. If there are binaries for it use it otherwise just tell the user we might need these binaries with different options.
- `rh workflow` should also represent in which stage we are currently in the project.

UI should be really attracting and good. with custom progress bars, tables etc.
