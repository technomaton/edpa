import simpleGit from 'simple-git';
import type { GitStatus } from '../src/types/edpa.js';

export function createGitClient(repoRoot: string) {
  const git = simpleGit(repoRoot);

  return {
    async status(): Promise<GitStatus> {
      const st = await git.status();
      const branch = st.current || 'unknown';
      const dirty = [...st.modified, ...st.not_added, ...st.created]
        .filter(f => f.startsWith('.edpa/'));
      return { branch, dirty, ahead: st.ahead };
    },

    async commit(message: string): Promise<string> {
      await git.add('.edpa/');
      const result = await git.commit(message);
      return result.commit || 'no changes';
    },

    async createBranch(name: string): Promise<string> {
      await git.checkoutLocalBranch(name);
      return name;
    },

    async currentBranch(): Promise<string> {
      const st = await git.status();
      return st.current || 'unknown';
    },

    async branches(): Promise<string[]> {
      const result = await git.branchLocal();
      return result.all;
    },

    async checkout(branch: string): Promise<void> {
      await git.checkout(branch);
    },
  };
}
